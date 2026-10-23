"""Graph wiring. Conditional edges contain routing logic only (they read `route` / state flags)."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent.graph.deps import Deps
from agent.graph.nodes import edit, factcheck, intake, produce, review, script, translate
from agent.graph.state import GraphState


def _route(default: str) -> Any:
    def pick(state: GraphState) -> str:
        r = state.get("route") or default
        return END if r == "end" else r

    return pick


def _clears_route(fn: Any) -> Any:
    """`route` is a one-shot hint: any node that does not set it resets it, so a stale value can
    never steer a later edge."""

    def node(state: Any) -> Any:
        out = fn(state)
        if isinstance(out, dict) and "route" not in out:
            out = {**out, "route": ""}
        return out

    node.__name__ = getattr(fn, "__name__", "node")
    return node


def entry(state: GraphState) -> str:
    """New user message: an existing script is edited, otherwise the request goes to intake."""
    return "chat_edit" if state.get("spec") else "intake"


def build_graph(
    deps: Deps, checkpointer: BaseCheckpointSaver[Any] | None = None
) -> CompiledStateGraph[Any, Any, Any, Any]:
    g: StateGraph[Any, Any, Any, Any] = StateGraph(GraphState)

    def add(name: str, fn: Any) -> None:
        g.add_node(name, _clears_route(fn))

    add("intake", intake.make_intake(deps))
    add("ingest_source", intake.make_ingest_source(deps))
    add("plan", script.make_plan(deps))
    add("write_script", script.make_write_script(deps))
    add("fact_check", factcheck.make_fact_check(deps))
    g.add_node("check_scene", factcheck.make_check_scene(deps))  # parallel Send branches: no route writes
    add("fact_reduce", factcheck.make_fact_reduce(deps))
    add("fix_script", script.make_fix_script(deps))
    add("translate", translate.make_translate(deps))
    add("present_script", review.make_present_script(deps))
    add("review_script", review.make_review_script(deps))
    add("narrate", produce.make_narrate(deps))
    add("layout_check", produce.make_layout_check(deps))
    add("render_preview", produce.make_render_preview(deps))
    add("validate_video", produce.make_validate_video(deps))
    add("present_video", review.make_present_video(deps))
    add("review_video", review.make_review_video(deps))
    add("render_final", produce.make_render_final(deps))
    add("done", produce.make_done(deps))
    add("chat_edit", edit.make_chat_edit(deps))
    add("apply_edit", edit.make_apply_edit(deps))

    g.add_conditional_edges(START, entry, ["intake", "chat_edit"])
    g.add_conditional_edges("intake", _route("ingest_source"), ["ingest_source", END])
    g.add_edge("ingest_source", "plan")
    g.add_edge("plan", "write_script")
    g.add_conditional_edges("write_script", _route("fact_check"), ["fact_check", END])
    g.add_conditional_edges("fact_check", factcheck.fan_out, ["check_scene", "fact_reduce"])
    g.add_edge("check_scene", "fact_reduce")
    g.add_conditional_edges(
        "fact_reduce", factcheck.route_after_fact, ["fix_script", "translate", "present_script", "narrate"]
    )
    g.add_edge("fix_script", "fact_check")
    g.add_conditional_edges(
        "translate", translate.route_after_translate, ["fix_script", "present_script", "narrate"]
    )
    g.add_edge("present_script", "review_script")
    g.add_conditional_edges(
        "review_script",
        _route("narrate"),
        ["narrate", "write_script", "chat_edit", "fact_reduce", "fix_script"],
    )
    g.add_conditional_edges("narrate", _route("layout_check"), ["layout_check", END])
    g.add_conditional_edges("layout_check", _route("render_preview"), ["render_preview", "fix_script", END])
    g.add_conditional_edges("render_preview", _route("validate_video"), ["validate_video", END])
    g.add_conditional_edges("render_final", _route("validate_video"), ["validate_video", END])
    g.add_conditional_edges("validate_video", _route("present_video"), ["present_video", "done", END])
    g.add_edge("present_video", "review_video")
    g.add_conditional_edges(
        "review_video", _route("render_final"), ["render_final", "write_script", "chat_edit", END]
    )
    g.add_edge("done", END)
    g.add_edge("chat_edit", "apply_edit")
    g.add_conditional_edges(
        "apply_edit",
        _route("end"),
        ["write_script", "translate", "fact_check", "narrate", "present_script", "present_video", END],
    )
    return g.compile(checkpointer=checkpointer)
