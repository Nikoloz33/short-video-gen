"""Command line: create a project from a source document and drive the agent without the web UI.

    uv run python -m agent.cli create --source data/fixtures/sources/handwashing-sop-en.md \
        --message "A 45-second Georgian training video with one quiz" [--approve script,video] [--fake]
    uv run python -m agent.cli chat <project_id> "make step 3 shorter"
    uv run python -m agent.cli resume <project_id> approve|regenerate
    uv run python -m agent.cli status <project_id>
    uv run python -m agent.cli spend
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agent.graph.runner import Runner, build_deps
from agent.llm.usage import Ledger
from agent.logging import configure, get_logger
from agent.settings import get_settings

log = get_logger("cli")


def _print(event: dict[str, Any], out: Any) -> None:
    t = event.get("type")
    if t == "token":
        out.write(event["text"])
        out.flush()
        return
    if t == "card":
        card = event["card"]
        out.write(f"\n  [card:{card.get('kind')}] {json.dumps(card, ensure_ascii=False)[:600]}\n")
    elif t == "render_progress":
        if event.get("stage") == "tts":
            out.write(
                f"\r  tts {event.get('done')}/{event.get('total')} (cache hits {event.get('cache_hits')})"
            )
        else:
            out.write(
                f"\r  {event.get('preset')} {event.get('stage')}: {event.get('renderedFrames', 0)}/{event.get('totalFrames', '?')}"
            )
        out.flush()
        return
    elif t == "render_done":
        out.write(
            f"\n  rendered {event.get('preset')} v{event.get('version')} in {event.get('durationMs')} ms {event.get('stages')}\n"
        )
    elif t in ("awaiting_review", "error", "done", "status"):
        out.write(f"\n» {json.dumps(event, ensure_ascii=False)}\n")
    elif t == "node":
        out.write(f"\n· {event['node']}")
    out.flush()


def _drive(runner: Runner, pid: str, events: Any, approve: set[str]) -> None:
    while True:
        pending = None
        for ev in events:
            _print(ev, sys.stdout)
            if ev.get("type") == "awaiting_review":
                pending = ev.get("kind")
        if pending and pending in approve:
            sys.stdout.write(f"\n» auto-approving {pending}\n")
            events = runner.run(pid, resume={"action": "approve", "user": "cli"})
            continue
        return


def main(argv: list[str] | None = None) -> int:
    configure(level="WARNING")
    p = argparse.ArgumentParser(prog="agent.cli")
    p.add_argument("--fake", action="store_true", help="fake model/TTS/renderer (no cost)")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--source", type=Path, required=True)
    c.add_argument("--message", required=True)
    c.add_argument("--approve", default="", help="comma list of reviews to auto-approve: script,video")
    ch = sub.add_parser("chat")
    ch.add_argument("project")
    ch.add_argument("message")
    ch.add_argument("--approve", default="")
    r = sub.add_parser("resume")
    r.add_argument("project")
    r.add_argument("action", choices=["approve", "regenerate"])
    r.add_argument("--approve", default="")
    rt = sub.add_parser("retry", help="continue a run that stopped on an error")
    rt.add_argument("project")
    rt.add_argument("--approve", default="")
    s = sub.add_parser("status")
    s.add_argument("project")
    sub.add_parser("spend")
    args = p.parse_args(argv)

    settings = get_settings()
    if args.fake:
        settings = settings.model_copy(update={"app_fake": True})
    if args.cmd == "spend":
        sys.stdout.write(f"${Ledger(settings.data_dir / 'metrics.db').total_usd():.4f} recorded\n")
        return 0
    runner = Runner(build_deps(settings))
    approve = {a.strip() for a in getattr(args, "approve", "").split(",") if a.strip()}
    if args.cmd == "create":
        pid = runner.deps.projects.create(args.source.stem)
        doc, _ = runner.deps.projects.add_source(
            pid, args.source.name, args.source.read_bytes(), runner.deps.router
        )
        sys.stdout.write(
            f"project {pid}: source {doc.doc_id} ({doc.lang}), {len(doc.redactions)} redaction(s)\n"
        )
        _drive(runner, pid, runner.run(pid, message=args.message), approve)
    elif args.cmd == "chat":
        _drive(runner, args.project, runner.run(args.project, message=args.message), approve)
    elif args.cmd == "resume":
        _drive(
            runner,
            args.project,
            runner.run(args.project, resume={"action": args.action, "user": "cli"}),
            approve,
        )
    elif args.cmd == "retry":
        _drive(runner, args.project, runner.run(args.project, retry=True), approve)
    elif args.cmd == "status":
        st = runner.state(args.project)
        sys.stdout.write(
            json.dumps(
                {k: st.get(k) for k in ("status", "request", "render", "tts_stats")}, indent=1, default=str
            )
            + "\n"
        )
        sys.stdout.write(json.dumps(runner.pending_interrupt(args.project)) + "\n")
    runner.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
