"""Hybrid retrieval: BM25 + vector, merged with reciprocal-rank fusion, optional Flash rerank."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, PrivateAttr
from rank_bm25 import BM25Okapi

from agent.llm.router import LLMRouter
from agent.llm.usage import Usage, merge_usage
from agent.prompts import load_prompt, source_block
from agent.rag.embeddings import Embedder
from agent.rag.store import ChunkStore
from agent.schemas.llm_io import RerankScores

RRF_K = 60


def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


class HybridRetriever(BaseRetriever):
    """LangChain retriever over ONE project's chunks. `last_usage` holds the cost of the last search."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    store: ChunkStore
    embedder: Embedder
    router: LLMRouter | None = None
    k: int = 5
    candidates: int = 12
    rerank: bool = False

    _bm25: BM25Okapi | None = PrivateAttr(default=None)
    _docs: list[Document] = PrivateAttr(default_factory=list)
    last_usage: Usage = Usage()

    def refresh(self) -> None:
        self._docs = self.store.chunks()
        self._bm25 = BM25Okapi([tokenize(d.page_content) for d in self._docs]) if self._docs else None

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        docs, usage = self.search(query)
        self.last_usage = usage
        return docs

    def search(self, query: str, k: int | None = None) -> tuple[list[Document], Usage]:
        if self._bm25 is None:
            self.refresh()
        if not self._docs:
            return [], Usage()
        k = k or self.k
        by_id = {str(d.id): d for d in self._docs}
        ranks: dict[str, float] = {}

        assert self._bm25 is not None
        scores = self._bm25.get_scores(tokenize(query))
        bm = sorted(range(len(self._docs)), key=lambda i: -scores[i])[: self.candidates]
        for r, i in enumerate(bm):
            if scores[i] > 0:
                cid = str(self._docs[i].id)
                ranks[cid] = ranks.get(cid, 0.0) + 1.0 / (RRF_K + r + 1)

        vec, usage = self.embedder.query(query)
        for r, (cid, _sim) in enumerate(self.store.vector_search(vec, self.candidates)):
            if cid in by_id:  # dedupe across both lists
                ranks[cid] = ranks.get(cid, 0.0) + 1.0 / (RRF_K + r + 1)

        merged = [by_id[c] for c, _ in sorted(ranks.items(), key=lambda x: -x[1])][: self.candidates]
        if self.rerank and self.router is not None and len(merged) > k:
            merged, u = self._rerank(query, merged)
            usage = merge_usage(usage, u)
        return merged[:k], usage

    def _rerank(self, query: str, docs: list[Document]) -> tuple[list[Document], Usage]:
        assert self.router is not None
        blocks = "\n".join(source_block(d.page_content, f"CHUNK {d.id}") for d in docs)
        prompt = load_prompt("rerank").render(query=query, chunks=blocks)
        r = self.router.structured("rerank", prompt, RerankScores)
        score: dict[str, Any] = {s.chunk_id: s.score for s in r.value.scores}
        ranked = sorted(docs, key=lambda d: -int(score.get(str(d.id), 0)))
        return ranked, r.usage
