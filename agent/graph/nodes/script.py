"""plan, write_script, fix_script."""

from __future__ import annotations

import time
from typing import Any

from agent.factcheck.checker import FactReport
from agent.graph.deps import Deps, say, status
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
        for _attempt in range(2):
            p = (
                prompt
                if not problems
                else prompt + "\n\nYour previous draft was invalid:\n- " + "\n- ".join(problems)
            )
            r = deps.router.structured("write_script", p, ScriptDraft)
            usage = merge_usage(usage, r.usage)
            try:
                spec = draft_to_spec(
                    r.value,
                    lang=lang,
                    source_lang=lang,
                    audience=req["audience"],
                    target_sec=req["target_sec"],
                    sources=sources,
                    version=_next_version(deps, pid),
                )
                break
            except DraftError as e:
                problems = e.problems
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
            "last_signature": "",
            "layout_issues": [],
            "script_approved": False,
            "versions": [{"version": spec.version, "note": "new script", "created": time.time()}],
            "usage": usage.model_dump(),
        }

    return write_script


def rewrite_scenes(deps: Deps, spec: VideoSpec, fix: ScriptFix) -> tuple[VideoSpec, list[str]]:
    """Applies LLM rewrites (by scene id, or 'new*' appended after `after`) deterministically."""
    scenes: list[Scene] = list(spec.scenes)
    changed: list[str] = []
    for rw in fix.rewrites:
        converted = draft_scenes([rw.scene], spec.lang)[0]
        idx = next((i for i, s in enumerate(scenes) if s.id == rw.scene_id), None)
        if idx is None:
            continue
        scenes[idx] = converted.model_copy(update={"id": rw.scene_id, "audio": None})
        changed.append(rw.scene_id)
    return renumber(spec.model_copy(update={"scenes": scenes})), changed


def make_fix_script(deps: Deps) -> Any:
    def fix_script(state: GraphState) -> dict[str, Any]:
        spec = spec_of(state)
        report = FactReport.model_validate(state.get("fact_report") or {"scenes": []})
        problems: dict[str, list[str]] = {s.scene_id: s.problems() for s in report.failing()}
        for issue in state.get("layout_issues", []):
            sid = issue.get("scene_id", "-")
            targets = [s.id for s in spec.scenes] if sid == "-" else [sid]
            for t in targets:
                problems.setdefault(t, []).append(f"{issue.get('field')}: {issue.get('message')}")
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
        try:
            new_spec, changed = rewrite_scenes(deps, spec, r.value)
        except DraftError as e:
            return {**say("The automatic fix produced an invalid scene: " + "; ".join(e.problems)),
                    "fix_loops": state.get("fix_loops", 0) + 1, "usage": r.usage.model_dump()}  # fmt: skip
        deps.projects.save_spec(state["project_id"], new_spec)
        card = {"kind": "fix", "scenes": changed, "note": r.value.note}
        return {
            **say(r.value.note, card),
            "spec": dump(new_spec),
            "fact_targets": changed,
            "fix_loops": state.get("fix_loops", 0) + 1,
            "last_signature": report.signature(),
            "layout_issues": [],
            "usage": r.usage.model_dump(),
        }

    return fix_script
