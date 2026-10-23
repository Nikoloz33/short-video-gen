"""Dependencies injected into node factories (no globals): router, storage, retrievers, TTS, renderer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.config import get_stream_writer

from agent.config import AppConfig, load_app
from agent.llm.router import LLMRouter
from agent.rag.embeddings import Embedder
from agent.rag.retrieval import HybridRetriever
from agent.rag.store import ChunkStore
from agent.render.worker import Renderer
from agent.settings import Settings
from agent.storage import ProjectStore
from agent.tts.narrator import Narrator


@dataclass
class Deps:
    settings: Settings
    router: LLMRouter
    projects: ProjectStore
    renderer: Renderer
    narrator: Narrator
    app: AppConfig = field(default_factory=load_app)
    rerank: bool = False
    _retrievers: dict[str, HybridRetriever] = field(default_factory=dict)
    _embedder: Embedder | None = None

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = Embedder(self.router, self.settings.data_dir / "cache" / "embeddings")
        return self._embedder

    def store(self, project_id: str) -> ChunkStore:
        return ChunkStore(self.settings.data_dir / "chroma", self.projects.dir(project_id), project_id)

    def retriever(self, project_id: str) -> HybridRetriever:
        r = self._retrievers.get(project_id)
        if r is None:
            r = HybridRetriever(
                store=self.store(project_id), embedder=self.embedder, router=self.router, rerank=self.rerank
            )
            self._retrievers[project_id] = r
        return r

    @property
    def media_root(self) -> Path:
        return self.settings.data_dir


def emit(event: dict[str, Any]) -> None:
    """Custom stream event (card / token / render_progress / status). No-op outside a stream."""
    try:
        writer = get_stream_writer()
    except Exception:
        return
    writer(event)


def say(text: str, card: dict[str, Any] | None = None) -> dict[str, Any]:
    """A chat message from the agent: streamed as tokens + stored in `messages` (with its card)."""
    for i, word in enumerate(text.split(" ")):
        emit({"type": "token", "text": word if i == 0 else f" {word}"})
    if card is not None:
        emit({"type": "card", "card": card})
    kwargs = {"card": card} if card is not None else {}
    return {"messages": [AIMessage(content=text, additional_kwargs=kwargs)]}


def status(value: str, **extra: Any) -> dict[str, Any]:
    emit({"type": "status", "status": value, **extra})
    return {"status": value}
