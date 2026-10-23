"""plan, write_script, fix_script."""

from __future__ import annotations

import re
import time
from typing import Any

from agent.factcheck.checker import FactReport
from agent.graph.deps import Deps, emit, say, status
from agent.graph.nodes.common import chunks_block, dump, icons_block, spec_of
from agent.graph.state import RESET, GraphState
from agent.llm.usage import Usage, merge_usage
from agent.prompts import load_prompt
from agent.schemas.llm_io import Plan, ScriptDraft, ScriptFix
from agent.schemas.video_spec import Lang, Scene, SourceRef, VideoSpec
from agent.script import (
    DraftError,
    draft_scenes,
    draft_to_spec,
    narration_budget_chars,
    outline,
    pace,
    renumber,
)

LANG_NAME = {"ka": "Georgian", "en": "English"}


def _next_version(deps: Deps, pid: str) -> int:
    root = deps.projects.dir(pid) / "versions"
    nums = [int(p.name[1:]) for p in root.glob("v*") if p.name[1:].isdigit()] if root.exists() else []
    return max(nums, default=0) + 1


def make_plan(deps: Deps) -> Any:
    def plan(state: GraphState) -> dict[str, Any]:
        req = state["request"]
        chunks = deps.store(state["project_id"]).chunks()
        r = deps.router.structured(
            "plan",
            load_prompt("plan").render(
                audience=req["audience"],
                target_sec=req["target_sec"],
                quiz_count=req["quiz_count"],
                source_lang=req["source_lang"],
                chunks=chunks_block(chunks),
            ),
            Plan,
        )
        p = r.value
        card = {
            "kind": "plan",
            "goal": p.goal,
            "steps": [s.title for s in p.steps],
            "quiz_topics": p.quiz_topics,
            "warnings": p.warnings,
            "target_sec": req["target_sec"],
            "language": req["target_lang"],
        }
        return {
            **say(p.summary, card),
            **status("scripting"),
            "plan": p.model_dump(),
            "usage": r.usage.model_dump(),
        }

    return plan


def make_write_script(deps: Deps) -> Any:
    def write_script(state: GraphState) -> dict[str, Any]:
        pid = state["project_id"]
        req = state["request"]
        lang: Lang = req["source_lang"]  # write + fact-check in the source language, translate later
        chunks = deps.store(pid).chunks()
        plan = Plan.model_validate(state["plan"])
        quiz_n = int(req.get("quiz_count") or 0)
        quiz_rule = (
            f"Include exactly {quiz_n} quiz checkpoint(s): each a quiz_question followed by its quiz_answer."
            if quiz_n
            else "Do not include quiz scenes."
        )
        if req["audience"] == "patient":
            quiz_rule += " End with the disclaimer scene."
        prompt = load_prompt("write_script").render(
            target_sec=req["target_sec"],
            lang_name=LANG_NAME[lang],
            plan=plan.model_dump_json(indent=1),
            chunks=chunks_block(chunks),
            quiz_rule=quiz_rule,
            char_budget=narration_budget_chars(req["target_sec"], lang),
            chars_per_sec=pace(lang),
            icons=icons_block(),
        )
        docs = deps.projects.sources(pid)
        sources = [SourceRef(doc_id=d.doc_id, title=d.title) for d in docs]
        usage = Usage()
        problems: list[str] = []
        spec: VideoSpec | None = None
        # Up to 3 drafts. Each one is gated BEFORE any fact-check or narration: valid scenes,
        # close to the requested length, every text fits its box. Problems go back with targets.
        for attempt in range(3):
            p = (
                prompt
                if not problems
                else prompt + "\n\nFix these problems in your previous draft:\n- " + "\n- ".join(problems)
            )
            r = deps.router.structured("write_script", p, ScriptDraft)
            usage = merge_usage(usage, r.usage)
            try:
                candidate = draft_to_spec(
                    r.value,
                    lang=lang,
                    source_lang=lang,
                    audience=req["audience"],
                    target_sec=req["target_sec"],
                    sources=sources,
                    version=_next_version(deps, pid),
                )
            except DraftError as e:
                problems = e.problems
                continue
            spec = candidate
            problems = draft_gate(deps, candidate, req["target_sec"])
            if not problems:
                break
            if attempt < 2:
                emit(
                    {
                        "type": "status",
                        "status": "scripting",
                        "detail": f"tightening the draft ({len(problems)} issue(s))",
                    }
                )
        if spec is None:
            return {**say("I could not produce a valid script: " + "; ".join(problems)), **status("error"),
                    "usage": usage.model_dump(), "route": "end"}  # fmt: skip
        deps.projects.save_spec(pid, spec)
        return {
            **status("fact_checking"),
            "spec": dump(spec),
            "fact_report": None,
            "fact_targets": [],
            "scene_reports": [RESET],
            "fix_loops": 0,
            "layout_loops": 0,
            "last_signature": "",
            "layout_issues": [],
            "script_approved": False,
            "versions": [{"version": spec.version, "note": "new script", "created": time.time()}],
            "usage": usage.model_dump(),
        }

    return write_script


TEXT_CODES = ("text_", "caption_", "unknown_icon")


def text_issues(deps: Deps, spec: VideoSpec) -> list[dict[str, Any]]:
    """Text-fit / icon problems only (durations are judged after narration measures them)."""
    issues = deps.renderer.check(
        spec, {"minTotalS": 0, "maxTotalS": 100000, "minSceneS": 0, "maxSceneS": 1000}
    )
    return [i for i in issues if str(i.get("code", "")).startswith(TEXT_CODES)]


def draft_gate(deps: Deps, spec: VideoSpec, target_sec: float) -> list[str]:
    """Cheap, deterministic checks of a fresh draft, phrased as instructions for the model."""
    problems: list[str] = []
    est = spec.total_s
    if est > target_sec * 1.2 + 5:
        cut = int((est - target_sec) * pace(spec.lang))
        problems.append(
            f"The script runs about {est:.0f} s but the requested length is {target_sec:.0f} s: cut about "
            f"{cut} characters of narration across the scenes, or drop a minor scene "
            "(keep every number, dose and prohibition)."
        )
    for issue in text_issues(deps, spec):
        problems.append(f"[{issue.get('scene_id')}] {layout_hint(issue)}")
    return problems


def rewrite_scenes(deps: Deps, spec: VideoSpec, fix: ScriptFix) -> tuple[VideoSpec, list[str], list[str]]:
    """Applies LLM rewrites by scene id. A rewrite that still cannot become a valid scene is skipped
    (the original scene stays) instead of discarding the whole fix. Returns (spec, changed, skipped)."""
    scenes: list[Scene] = list(spec.scenes)
    changed: list[str] = []
    skipped: list[str] = []
    for rw in fix.rewrites:
        idx = next((i for i, s in enumerate(scenes) if s.id == rw.scene_id), None)
        if idx is None:
            continue
        try:
            converted = draft_scenes([rw.scene], spec.lang)[0]
        except DraftError:
            skipped.append(rw.scene_id)
            continue
        scenes[idx] = converted.model_copy(update={"id": rw.scene_id, "audio": None})
        changed.append(rw.scene_id)
    return renumber(spec.model_copy(update={"scenes": scenes})), changed, skipped


def layout_hint(issue: dict[str, Any]) -> str:
    """Layout problems with a concrete target: models shorten reliably only when given a length."""
    msg = str(issue.get("message", ""))
    base = f"{issue.get('field')}: {msg}"
    m = re.search(r'\((\d+)/(\d+) lines\): "(.*)"$', msg)
    if m:
        lines, max_lines, text = int(m.group(1)), int(m.group(2)), m.group(3)
        target = int(len(text) * max_lines / max(lines, 1) * 0.85)
        base += f" -> rewrite it in at most {target} characters (keep every number and prohibition)"
    if issue.get("code") == "total_duration":
        base += " -> shorten the narration of every scene by about a third"
    return base


def make_fix_script(deps: Deps) -> Any:
    def fix_script(state: GraphState) -> dict[str, Any]:
        spec = spec_of(state)
        report = FactReport.model_validate(state.get("fact_report") or {"scenes": []})
        requests = state.get("fix_requests") or []
        problems: dict[str, list[str]] = {}
        if requests:
            # The user decided what to change (e.g. "remove this claim"): only those scenes.
            for req in requests:
                problems.setdefault(str(req["scene_id"]), []).append(str(req["instruction"]))
        else:
            problems = {s.scene_id: s.problems() for s in report.failing()}
        for issue in state.get("layout_issues", []):
            sid = issue.get("scene_id", "-")
            targets = [s.id for s in spec.scenes] if sid == "-" else [sid]
            for t in targets:
                problems.setdefault(t, []).append(layout_hint(issue))
        # Text-fit / translation repairs have their own budget; fact repairs use fix_loops.
        text_or_translation = bool(state.get("layout_issues")) or any(
            s.translation_problems for s in report.scenes
        )
        text = "\n".join(f"[{sid}]\n- " + "\n- ".join(p) for sid, p in problems.items())
        r = deps.router.structured(
            "fix_script",
            load_prompt("fix_script").render(
                lang_name=LANG_NAME[spec.lang],
                outline=outline(spec),
                problems=text,
                chunks=chunks_block(deps.store(state["project_id"]).chunks()),
                icons=icons_block(),
            ),
            ScriptFix,
        )
        new_spec, changed, skipped = rewrite_scenes(deps, spec, r.value)
        deps.projects.save_spec(state["project_id"], new_spec)
        note = r.value.note + (f" (Kept the original of {', '.join(skipped)}.)" if skipped else "")
        card = {"kind": "fix", "scenes": changed, "note": note}
        return {
            **say(note, card),
            "spec": dump(new_spec),
            # Only rewritten scenes are re-checked; with no change there is nothing to re-check.
            "fact_targets": changed or ["-"],
            "fix_loops": state.get("fix_loops", 0) + (0 if text_or_translation else 1),
            "layout_loops": state.get("layout_loops", 0) + (1 if text_or_translation else 0),
            "last_signature": report.signature(),
            "layout_issues": [],
            "fix_requests": [],
            "usage": r.usage.model_dump(),
        }

    return fix_script
