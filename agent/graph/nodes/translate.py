"""translate: target language + back-translation gates (problems become fact-report items)."""

from __future__ import annotations

import time
from typing import Any

from agent.factcheck.checker import FactReport
from agent.graph.deps import Deps, say, status
from agent.graph.nodes.common import dump, spec_of, target_lang
from agent.graph.state import GraphState
from agent.translate import LANG_NAME, translate_spec


def make_translate(deps: Deps) -> Any:
    def translate(state: GraphState) -> dict[str, Any]:
        spec = spec_of(state)
        target = target_lang(state, spec.lang)
        out, problems, usage = translate_spec(spec, target, deps.router)
        out = out.model_copy(update={"version": spec.version + 1})
        deps.projects.save_spec(state["project_id"], out)
        report = FactReport.model_validate(state.get("fact_report") or {"scenes": []})
        for s in report.scenes:
            s.translation_problems = problems.get(s.scene_id, [])
        card = {"kind": "translation", "to": target, "problems": problems}
        msg = f"Translated to {LANG_NAME[target]}" + (
            f"; {len(problems)} scene(s) need a look."
            if problems
            else "; numbers, names and negations check out."
        )
        return {
            **say(msg, card),
            **status("translating"),
            "spec": dump(out),
            "fact_report": report.model_dump(),
            "versions": [{"version": out.version, "note": f"translated to {target}", "created": time.time()}],
            "usage": usage.model_dump(),
        }

    return translate


def route_after_translate(state: GraphState) -> str:
    report = FactReport.model_validate(state.get("fact_report") or {"scenes": []})
    if any(s.translation_problems for s in report.scenes) and state.get("fix_loops", 0) < 2:
        return "fix_script"
    return "narrate" if state.get("script_approved") else "present_script"
