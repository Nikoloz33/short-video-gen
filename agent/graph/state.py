"""Graph state. JSON-serialisable (dicts / lists / primitives) so the SQLite checkpointer can persist it;
Pydantic models are rebuilt inside nodes."""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from agent.llm.usage import Usage, merge_usage

RESET = {"__reset__": True}


def reports_reducer(a: list[dict[str, Any]] | None, b: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Accumulates per-scene fact reports from parallel `Send` branches; [RESET] clears the list."""
    if b and b[0] == RESET:
        return []
    return [*(a or []), *(b or [])]


def usage_reducer(a: dict[str, Any] | None, b: dict[str, Any] | None) -> dict[str, Any]:
    ua = Usage.model_validate(a) if a else None
    ub = Usage.model_validate(b) if b else None
    return merge_usage(ua, ub).model_dump()


class GraphState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    project_id: str
    #: What the user asked for: target_lang, target_sec, audience, quiz_count.
    request: dict[str, Any]
    indexed_docs: list[str]
    plan: dict[str, Any] | None
    #: The current VideoSpec (model_dump(mode="json")).
    spec: dict[str, Any] | None
    fact_report: dict[str, Any] | None
    scene_reports: Annotated[list[dict[str, Any]], reports_reducer]
    #: Scene ids to (re)check; empty = every scene.
    fact_targets: list[str]
    fix_loops: int
    #: Layout-fix attempts (separate budget from fact-check fixes).
    layout_loops: int
    last_signature: str
    layout_issues: list[dict[str, Any]]
    #: User-requested scene changes for fix_script: [{scene_id, instruction}] (e.g. remove a claim).
    fix_requests: list[dict[str, Any]]
    script_approved: bool
    #: One entry per saved spec version: {version, note, created}.
    versions: Annotated[list[dict[str, Any]], operator.add]
    #: Last render results: {"preview": {...}, "final": {...}, "last": "preview"|"final", "version": N}.
    render: dict[str, Any]
    tts_stats: dict[str, Any]
    edit: dict[str, Any] | None
    #: Routing hint written by nodes (routing functions only read it).
    route: str
    usage: Annotated[dict[str, Any], usage_reducer]
    status: str
    error: str | None
