"""Per-project chunk store: Chroma (cosine, embeddings passed explicitly) + a JSON copy of the chunks
for BM25 and citation lookup. One collection per project, so projects can never see each other."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import chromadb
from langchain_core.documents import Document

from agent.logging import get_logger

log = get_logger("rag.store")


def _collection_name(project_id: str) -> str:
    safe = "".join(ch if ch.isalnum() else "-" for ch in project_id)[:56]
    return f"p-{safe}".ljust(3, "x")


class ChunkStore:
    def __init__(self, chroma_dir: Path, project_dir: Path, project_id: str) -> None:
        self.project_id = project_id
        self._json = project_dir / "chunks.json"
        chroma_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(chroma_dir))
        self._col = self._client.get_or_create_collection(
            _collection_name(project_id), metadata={"hnsw:space": "cosine"}, embedding_function=None
        )

    # ---- chunks (JSON) --------------------------------------------------------------------------
    def chunks(self) -> list[Document]:
        if not self._json.exists():
            return []
        rows = json.loads(self._json.read_text("utf-8"))
        return [Document(page_content=r["text"], id=r["id"], metadata=r["meta"]) for r in rows]

    def chunk(self, chunk_id: str) -> Document | None:
        return next((d for d in self.chunks() if d.id == chunk_id), None)

    def doc_ids(self) -> set[str]:
        return {str(d.metadata["doc_id"]) for d in self.chunks()}

    # ---- writes ---------------------------------------------------------------------------------
    def add(self, docs: list[Document], vectors: list[list[float]]) -> None:
        if not docs:
            return
        existing = {d.id: d for d in self.chunks()}
        for d in docs:
            existing[d.id] = d
        self._json.parent.mkdir(parents=True, exist_ok=True)
        rows = [{"id": d.id, "text": d.page_content, "meta": d.metadata} for d in existing.values()]
        self._json.write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")
        self._col.upsert(
            ids=[str(d.id) for d in docs],
            embeddings=vectors,  # type: ignore[arg-type]
            documents=[d.page_content for d in docs],
            metadatas=[dict(d.metadata) for d in docs],
        )

    # ---- vector search --------------------------------------------------------------------------
    def vector_search(self, vector: list[float], k: int) -> list[tuple[str, float]]:
        n = min(k, max(1, self._col.count()))
        for attempt in range(5):
            try:
                res: Any = self._col.query(query_embeddings=[vector], n_results=n)  # type: ignore[arg-type]
                ids = res["ids"][0]
                dists = res["distances"][0]
                return [(str(i), 1.0 - float(dd)) for i, dd in zip(ids, dists, strict=True)]
            except Exception as e:
                # Chroma can race right after an upsert ("hnsw segment reader: nothing found on disk").
                if "nothing found on disk" not in str(e).lower() or attempt == 4:
                    raise
                log.warning("chroma not ready, retrying", attempt=attempt + 1)
                time.sleep(0.2 * (attempt + 1))
        return []  # pragma: no cover
