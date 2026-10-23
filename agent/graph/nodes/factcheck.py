"""fact_check (dispatch) -> check_scene x N (Send) -> fact_reduce."""

from __future__ import annotations

from typing import Any

from langgraph.types import Send
from pydantic import TypeAdapter

from agent.factcheck.checker import FactReport, SceneReport, check_scene
from agent.graph.deps import Deps, emit, say, status
from agent.graph.nodes.common import spec_of
from agent.graph.state import RESET, GraphState
from agent.schemas.video_spec import Scene

_SCENE: TypeAdapter[Scene] = TypeAdapter(Scene)


def make_fact_check(deps: Deps) -> Any:
    def fact_check(state: GraphState) -> dict[str, Any]:
        return {**status("fact_checking"), "scene_reports": [RESET]}

    return fact_check


def fan_out(state: GraphState) -> list[Send] | str:
    """Routing only: one Send per target scene (all scenes when no targets)."""
    spec = state.get("spec") or {"scenes": []}
    targets = set(state.get("fact_targets") or [])
    scenes = [s for s in spec["scenes"] if not targets or s["id"] in targets]
    if not scenes:
        return "fact_reduce"
    return [Send("check_scene", {"project_id": state["project_id"], "scene": s}) for s in scenes]


def make_check_scene(deps: Deps) -> Any:
    def check_scene_node(payload: dict[str, Any]) -> dict[str, Any]:
        scene = _SCENE.validate_python(payload["scene"])
        report, usage = check_scene(scene, deps.retriever(payload["project_id"]), deps.router)
        emit({"type": "fact_progress", "scene_id": scene.id, "ok": report.ok})
        return {"scene_reports": [report.model_dump()], "usage": usage.model_dump()}

    return check_scene_node


def make_fact_reduce(deps: Deps) -> Any:
    def fact_reduce(state: GraphState) -> dict[str, Any]:
        spec = spec_of(state)
        prev = FactReport.model_validate(state.get("fact_report") or {"scenes": []})
        updates = [SceneReport.model_validate(r) for r in state.get("scene_reports", [])]
        report = prev.merged(updates, [s.id for s in spec.scenes])
        counts = report.counts()
        failing = report.failing()
        store = deps.store(state["project_id"])
        card = {
            "kind": "fact_check",
            "ok": report.ok,
            "counts": counts,
            "scenes": [
                {
                    "scene_id": s.scene_id,
                    "ok": s.ok and not s.translation_problems,
                    "claims": [
                        {
                            "text": c.text,
                            "verdict": c.verdict,
                            "why": c.why,
                            "gate": c.gate,
                            "quote": c.quote,
                            "chunk_id": c.chunk_id,
                            "source": (
                                ch.page_content[:400]
                                if c.chunk_id and (ch := store.chunk(c.chunk_id))
                                else None
                            ),
                        }
                        for c in s.claims
                    ],
                    "translation_problems": s.translation_problems,
                }
                for s in report.scenes
            ],
        }
        n = sum(counts.values())
        text = (
            f"Fact-check: all {n} claims are supported by your source."
            if report.ok
            else f"Fact-check: {len(failing)} scene(s) need attention ({n - counts.get('supported', 0)} of {n} claims)."
        )
        return {**say(text, card), "fact_report": report.model_dump(), "fact_targets": []}

    return fact_reduce


def route_after_fact(state: GraphState) -> str:
    report = FactReport.model_validate(state.get("fact_report") or {"scenes": []})
    spec = state.get("spec") or {}
    if not report.ok:
        stuck = report.signature() == state.get("last_signature")
        if state.get("fix_loops", 0) < 2 and not stuck:
            return "fix_script"
    if state.get("script_approved"):
        return "narrate"
    if spec.get("lang") != state.get("request", {}).get("target_lang", spec.get("lang")):
        return "translate"
    return "present_script"
