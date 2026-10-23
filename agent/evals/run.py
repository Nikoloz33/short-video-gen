"""Evals.

    uv run python -m agent.evals.run              # offline: deterministic gates only (free)
    uv run python -m agent.evals.run --live       # full checker (Flash claims + RAG + Argon verdict)

Mutation suite (data/fixtures/evals/mutations.json): every case pairs a correct claim with a
corrupted one (wrong dose/number, flipped negation, invented step, swapped order, wrong drug, also
in Georgian). Recall = corrupted claims rejected; precision = rejected claims that really were
corrupted. Production metrics (render p50/p90, realtime factor, cost per project) come from
data/metrics.db. Writes docs/evals/report.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from agent.factcheck.gates import check_claim
from agent.logging import configure, get_logger
from agent.metrics import percentile, renders
from agent.settings import REPO_ROOT, Settings, get_settings

log = get_logger("evals")
FIXTURES = REPO_ROOT / "data" / "fixtures"
REPORT = REPO_ROOT / "docs" / "evals" / "report.md"


@dataclass
class Outcome:
    kind: str
    source: str
    good_ok: bool
    bad_rejected: bool
    detail: str


def _sentences(text: str) -> list[str]:
    return [s.strip(" -#\n") for s in re.split(r"(?<=[.;:])\s+|\n", text) if len(s.strip()) > 3]


def gates_only(claim: str, source: str) -> tuple[bool, str]:
    """Offline verdict: the source sentence most similar to the claim plays the LLM's quote."""
    quote = max(_sentences(source), key=lambda s: fuzz.token_set_ratio(claim.lower(), s.lower()))
    g = check_claim(claim, source, quote)
    return g.ok, g.why or ""


def run_offline(cases: list[dict[str, Any]]) -> list[Outcome]:
    out = []
    for c in cases:
        src = (FIXTURES / "sources" / c["source"]).read_text("utf-8")
        good_ok, _ = gates_only(c["good"], src)
        bad_ok, why = gates_only(c["bad"], src)
        out.append(Outcome(c["kind"], c["source"], good_ok, not bad_ok, why))
    return out


def run_live(cases: list[dict[str, Any]], settings: Settings) -> list[Outcome]:
    from agent.factcheck.checker import check_scene
    from agent.graph.runner import build_deps
    from agent.rag.chunking import chunk_pages
    from agent.rag.loaders import Page
    from agent.schemas.video_spec import StepCardScene

    tmp = Path(tempfile.mkdtemp(prefix="evals-"))
    deps = build_deps(settings.model_copy(update={"data_dir": tmp, "llm_cache": True}))
    retrievers = {}
    for name in sorted({c["source"] for c in cases}):
        pid = deps.projects.create(name)
        doc, _ = deps.projects.add_source(pid, name, (FIXTURES / "sources" / name).read_bytes())
        chunks = chunk_pages([Page(p["number"], p["text"]) for p in doc.pages], project_id=pid, doc_id=doc.doc_id,
                             language=doc.lang)  # fmt: skip
        vecs, _ = deps.embedder.embed([c.page_content for c in chunks], "RETRIEVAL_DOCUMENT")
        deps.store(pid).add(chunks, vecs)
        r = deps.retriever(pid)
        r.refresh()
        retrievers[name] = r

    def verdict(claim: str, source: str, i: int) -> tuple[bool, str]:
        scene = StepCardScene(id=f"e{i}", template="step_card", step_no=1, total_steps=1, icon="check",
                              text=claim[:140], narration=claim, evidence=[], duration_s=5)  # fmt: skip
        report, _ = check_scene(scene, retrievers[source], deps.router)
        bad = [c for c in report.claims if c.verdict != "supported"]
        return report.ok, "; ".join(f"{c.verdict}: {c.why}" for c in bad)

    out = []
    for i, c in enumerate(cases):
        good_ok, _ = verdict(c["good"], c["source"], 2 * i)
        bad_ok, why = verdict(c["bad"], c["source"], 2 * i + 1)
        out.append(Outcome(c["kind"], c["source"], good_ok, not bad_ok, why))
        log.info("case", kind=c["kind"], good_ok=good_ok, bad_rejected=not bad_ok)
    return out


def summarize(outcomes: list[Outcome]) -> dict[str, Any]:
    tp = sum(o.bad_rejected for o in outcomes)  # corrupted and rejected
    fn = sum(not o.bad_rejected for o in outcomes)
    fp = sum(not o.good_ok for o in outcomes)  # correct but rejected
    by_kind: dict[str, list[Outcome]] = defaultdict(list)
    for o in outcomes:
        by_kind[o.kind].append(o)
    return {
        "cases": len(outcomes),
        "recall": tp / max(1, tp + fn),
        "precision": tp / max(1, tp + fp),
        "false_rejections": fp,
        "by_kind": {k: {"n": len(v), "recall": sum(o.bad_rejected for o in v) / len(v),
                        "good_accepted": sum(o.good_ok for o in v) / len(v)} for k, v in sorted(by_kind.items())},
    }  # fmt: skip


def production_metrics(settings: Settings) -> dict[str, Any]:
    db = settings.data_dir / "metrics.db"
    if not db.exists():
        return {}
    rows = renders(db)
    out: dict[str, Any] = {"renders": len(rows)}
    for preset in ("preview", "final"):
        rs = [r for r in rows if r["preset"] == preset]
        walls = [r["wall_ms"] / 1000 for r in rs]
        rt = [r["video_s"] / max(0.001, r["wall_ms"] / 1000) for r in rs]
        out[preset] = {
            "n": len(rs),
            "wall_p50_s": percentile(walls, 0.5),
            "wall_p90_s": percentile(walls, 0.9),
            "realtime_p50": percentile(rt, 0.5),
            "duration_in_range": (sum(30 <= r["video_s"] <= 300 for r in rs) / len(rs)) if rs else None,
        }
    with sqlite3.connect(db) as c:
        per_thread = [
            v
            for (v,) in c.execute("SELECT SUM(cost_usd) FROM usage WHERE thread_id != '-' GROUP BY thread_id")
        ]
        out["cost_per_project_p50"] = percentile(per_thread, 0.5)
        out["total_spend_usd"] = c.execute("SELECT COALESCE(SUM(cost_usd),0) FROM usage").fetchone()[0]
    return out


def _fmt(v: Any, pct: bool = False) -> str:
    if v is None:
        return "—"
    if pct:
        return f"{100 * v:.0f} %"
    return f"{v:.2f}" if isinstance(v, float) else str(v)


def write_report(results: dict[str, dict[str, Any]], prod: dict[str, Any]) -> str:
    lines = [
        "# Evaluation report",
        "",
        f"_Generated {time.strftime('%Y-%m-%d %H:%M')} by `uv run python -m agent.evals.run`._",
        "",
        "## Fact-check mutation suite",
        "",
        "Each case pairs a correct claim from a synthetic source with a corrupted version. **Recall** = share",
        "of corrupted claims rejected; **precision** = share of rejections that were really corrupted.",
        "",
        "| mode | cases | recall | precision | correct claims wrongly rejected |",
        "|---|---|---|---|---|",
    ]
    for mode, s in results.items():
        lines.append(
            f"| {mode} | {s['cases']} | {_fmt(s['recall'], True)} | {_fmt(s['precision'], True)} | {s['false_rejections']} |"
        )
    for mode, s in results.items():
        lines += [
            "",
            f"### {mode}: by mutation kind",
            "",
            "| kind | n | recall | correct accepted |",
            "|---|---|---|---|",
        ]
        for k, v in s["by_kind"].items():
            lines.append(f"| {k} | {v['n']} | {_fmt(v['recall'], True)} | {_fmt(v['good_accepted'], True)} |")
    lines += [
        "",
        "`gates only` is the deterministic layer alone (numbers/units, names, negation polarity): it cannot",
        "see invented steps or swapped order — that is the LLM verdict's job in `full checker`.",
        "",
        "## Production metrics (data/metrics.db)",
        "",
    ]
    if prod:
        lines += [
            "| preset | renders | wall p50 | wall p90 | realtime p50 | duration in 30-60 s |",
            "|---|---|---|---|---|---|",
        ]
        for preset in ("preview", "final"):
            p = prod.get(preset, {})
            lines.append(f"| {preset} | {p.get('n', 0)} | {_fmt(p.get('wall_p50_s'))} s | {_fmt(p.get('wall_p90_s'))} s | "
                         f"{_fmt(p.get('realtime_p50'))}× | {_fmt(p.get('duration_in_range'), True)} |")  # fmt: skip
        lines += ["", f"Cost per project (p50): ${_fmt(prod.get('cost_per_project_p50'))} · total recorded spend: "
                  f"${_fmt(prod.get('total_spend_usd'))}"]  # fmt: skip
    else:
        lines.append("No production runs recorded yet.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    configure(level="WARNING")
    p = argparse.ArgumentParser()
    p.add_argument(
        "--live", action="store_true", help="also run the full checker against Vertex AI (costs ~$0.5)"
    )
    p.add_argument("--out", type=Path, default=REPORT)
    args = p.parse_args(argv)
    settings = get_settings()
    cases = json.loads((FIXTURES / "evals" / "mutations.json").read_text("utf-8"))["cases"]
    results = {"gates only": summarize(run_offline(cases))}
    if args.live:
        results["full checker"] = summarize(run_live(cases, settings))
    report = write_report(results, production_metrics(settings))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, "utf-8")
    sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
