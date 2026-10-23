"""Human checkpoints. `present_*` posts the card once; `review_*` only calls interrupt() (a node is
re-executed from the top on resume, so side effects must not live there)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from agent.factcheck.checker import FactReport
from agent.graph.deps import Deps, say, status
from agent.graph.nodes.common import spec_of
from agent.graph.state import GraphState
from agent.script import scene_texts


def make_present_script(deps: Deps) -> Any:
    def present_script(state: GraphState) -> dict[str, Any]:
        spec = spec_of(state)
        report = FactReport.model_validate(state.get("fact_report") or {"scenes": []})
        card = {
            "kind": "script",
            "version": spec.version,
            "title": spec.title,
            "lang": spec.lang,
            "estimated_s": round(spec.total_s, 1),
            "fact_ok": report.ok,
            "scenes": [
                {
                    "id": s.id,
                    "template": s.template,
                    "texts": scene_texts(s),
                    "narration": s.narration,
                    "icon": getattr(s, "icon", None),
                }
                for s in spec.scenes
            ],
        }
        text = (
            "Here is the script. Approve it to generate narration and a preview, or tell me what to change."
            if report.ok
            else "Here is the script. Some claims are still not supported by the source — please review the "
            "fact-check card; a final export stays blocked until every claim is supported."
        )
        return {**say(text, card), **status("awaiting_script_review")}

    return present_script


def make_review_script(deps: Deps) -> Any:
    def review_script(state: GraphState) -> dict[str, Any]:
        spec = state.get("spec") or {}
        answer = interrupt({"kind": "script", "version": spec.get("version")})
        action = (answer or {}).get("action", "approve")
        if action == "approve":
            return {"script_approved": True, "route": "narrate", **status("narrating")}
        if action == "regenerate":
            return {"route": "write_script", **status("scripting")}
        return {"messages": [HumanMessage(content=str(answer.get("text", "")))], "route": "chat_edit"}

    return review_script


def make_present_video(deps: Deps) -> Any:
    def present_video(state: GraphState) -> dict[str, Any]:
        r = state.get("render", {})
        prev = r.get("preview", {})
        card = {"kind": "video", "version": r.get("version"), "preset": "preview", "checks": prev.get("checks", []),
                "stages": prev.get("stages", {}), "tts": state.get("tts_stats", {})}  # fmt: skip
        return {**say("The preview is ready. Approve it for the final export, or ask for changes.", card),
                **status("awaiting_video_review")}  # fmt: skip

    return present_video


def make_review_video(deps: Deps) -> Any:
    def review_video(state: GraphState) -> dict[str, Any]:
        r = state.get("render", {})
        answer = interrupt({"kind": "video", "version": r.get("version")})
        action = (answer or {}).get("action", "approve")
        if action == "approve":
            report = FactReport.model_validate(state.get("fact_report") or {"scenes": []})
            if not report.ok:
                return {**say("I can't export the final video yet: some claims are not supported by the "
                              "source. Edit or remove them first."), **status("blocked"), "route": "end"}  # fmt: skip
            approver = str((answer or {}).get("user", "local"))
            deps.projects.record_approval(state["project_id"], int(r.get("version") or 0), approver)
            return {"route": "render_final", **status("rendering_final")}
        if action == "regenerate":
            return {"route": "write_script", "script_approved": False, **status("scripting")}
        return {"messages": [HumanMessage(content=str(answer.get("text", "")))], "route": "chat_edit"}

    return review_video
