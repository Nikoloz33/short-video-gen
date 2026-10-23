"""Small helpers shared by nodes."""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from langchain_core.messages import AnyMessage, HumanMessage, trim_messages

from agent.catalog import icon_prompt_list
from agent.graph.state import GraphState
from agent.prompts import source_block
from agent.schemas.video_spec import Lang, VideoSpec

HISTORY_TOKEN_BUDGET = 3000


def spec_of(state: GraphState) -> VideoSpec:
    raw = state.get("spec")
    if raw is None:
        raise ValueError("no spec in state")
    return VideoSpec.model_validate(raw)


def dump(spec: VideoSpec) -> dict[str, Any]:
    return spec.model_dump(mode="json")


def last_user_text(state: GraphState) -> str:
    for m in reversed(state.get("messages", [])):
        if isinstance(m, HumanMessage):
            return str(m.content)
    return ""


def history_text(messages: list[AnyMessage]) -> str:
    """Recent chat, trimmed to a token budget (the spec in state is the long-term memory)."""
    trimmed = trim_messages(
        messages,
        max_tokens=HISTORY_TOKEN_BUDGET,
        token_counter=lambda ms: sum(len(str(m.content)) // 4 + 4 for m in ms),
        strategy="last",
        start_on="human",
        include_system=False,
        allow_partial=False,
    )
    return "\n".join(f"{'user' if isinstance(m, HumanMessage) else 'agent'}: {m.content}" for m in trimmed)


def chunks_block(docs: list[Document], limit: int = 60) -> str:
    return "\n".join(source_block(d.page_content, f"CHUNK {d.id}") for d in docs[:limit])


def icons_block() -> str:
    return icon_prompt_list()


def target_lang(state: GraphState, default: Lang = "en") -> Lang:
    lang = state.get("request", {}).get("target_lang")
    return lang if lang in ("ka", "en") else default
