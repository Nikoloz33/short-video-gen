"""Human checkpoints. `present_*` posts the card once; `review_*` only calls interrupt() (a node is
re-executed from the top on resume, so side effects must not live there)."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from agent.factcheck.checker import FactReport
from agent.graph.deps import Deps, say, status
from agent.graph.nodes.common import spec_of
from agent.graph.state import RESET, GraphState
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


CLAIM_ACTIONS = {"keep_claim", "keep_flagged", "remove_claim", "remove_flagged", "fix_flagged"}


def decide_claims(
    deps: Deps, state: GraphState, action: str, answer: dict[str, Any], user: str
) -> dict[str, Any]:
    """The reviewer's decision on flagged claims — instant for keeps, one targeted rewrite for
    removals. Every decision is audit-logged with who made it."""
    report = FactReport.model_validate(state.get("fact_report") or {"scenes": []})
    version = int((state.get("spec") or {}).get("version") or 0)
    pid = state["project_id"]
    scene_id = answer.get("scene_id")
    index = answer.get("index")
    one = action in ("keep_claim", "remove_claim")
    picked = [(s, i, c) for s, i, c in report.flagged() if not one or (s.scene_id == scene_id and i == index)]
    for s, _i, c in picked:
        deps.projects.audit_event(pid, f"claim_{action.split('_')[0]}", version=version, user=user,
                                  scene_id=s.scene_id, claim=c.text, verdict=c.verdict)  # fmt: skip
    # Decisions replace the automatic loop: never fall back into it from here.
    base: dict[str, Any] = {"fix_loops": max(1, state.get("fix_loops", 0)), "scene_reports": [RESET]}
    if action in ("keep_claim", "keep_flagged"):
        report.confirm(scene_id if one else None, index if one else None, user)
        out = {**base, "fact_report": report.model_dump()}
        if action == "keep_flagged":
            return {**out, "script_approved": True, "route": "narrate", **status("narrating")}
        return {**out, "route": "fact_reduce"}  # re-post the ledger, then back to this review
    if action == "fix_flagged":
        return {**base, "fix_loops": 0, "fix_requests": [], "route": "fix_script", **status("fact_checking")}
    requests = [
        {"scene_id": s.scene_id,
         "instruction": f'Remove this claim from the scene entirely (do not reword it): "{c.text}". Keep everything else.'}
        for s, _i, c in picked
    ]  # fmt: skip
    return {**base, "fix_requests": requests, "route": "fix_script", **status("fact_checking")}


def make_review_script(deps: Deps) -> Any:
    def review_script(state: GraphState) -> dict[str, Any]:
        spec = state.get("spec") or {}
        answer = interrupt({"kind": "script", "version": spec.get("version")})
        answer = answer or {}
        action = answer.get("action", "approve")
        user = str(answer.get("user", "local"))
        if action == "approve":
            return {"script_approved": True, "route": "narrate", **status("narrating")}
        if action == "regenerate":
            return {"route": "write_script", **status("scripting")}
        if action in CLAIM_ACTIONS:
            return decide_claims(deps, state, action, answer, user)
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
