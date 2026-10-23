"""Embeddings through the router: one text per request (Vertex limit), a small thread pool, and a
disk cache keyed by sha256(model|task|text)."""

from __future__ import annotations

import contextvars
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent.llm.router import LLMRouter
from agent.llm.types import TaskType
from agent.llm.usage import Usage, merge_usage


class Embedder:
    def __init__(self, router: LLMRouter, cache_dir: Path | None, workers: int = 4) -> None:
        self.router = router
        self.cache_dir = cache_dir
        self.workers = workers
        self.model = router.models.role("embeddings").model
        self.cache_hits = 0

    def _key(self, text: str, task: TaskType) -> str:
        return hashlib.sha256(f"{self.model}|{task}|{text}".encode()).hexdigest()

    def _cached(self, key: str) -> list[float] | None:
        if not self.cache_dir:
            return None
        p = self.cache_dir / key[:2] / f"{key}.json"
        if p.exists():
            vec: list[float] = json.loads(p.read_text("utf-8"))
            return vec
        return None

    def _store(self, key: str, vec: list[float]) -> None:
        if not self.cache_dir:
            return
        p = self.cache_dir / key[:2] / f"{key}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(vec), "utf-8")

    def embed(self, texts: list[str], task: TaskType) -> tuple[list[list[float]], Usage]:
        out: list[list[float] | None] = [None] * len(texts)
        todo: list[int] = []
        for i, t in enumerate(texts):
            hit = self._cached(self._key(t, task))
            if hit is not None:
                out[i] = hit
                self.cache_hits += 1
            else:
                todo.append(i)
        usage = Usage()

        def one(i: int) -> tuple[int, list[float], Usage]:
            vec, u = self.router.embed(texts[i], task)
            self._store(self._key(texts[i], task), vec)
            return i, vec, u

        if todo:
            ctx = contextvars.copy_context()  # keep the run budget + thread id inside the pool
            with ThreadPoolExecutor(max_workers=self.workers) as pool:
                for i, vec, u in pool.map(lambda i: ctx.copy().run(one, i), todo):
                    out[i] = vec
                    usage = merge_usage(usage, u)
        return [v for v in out if v is not None], usage

    def query(self, text: str) -> tuple[list[float], Usage]:
        vecs, u = self.embed([text], "RETRIEVAL_QUERY")
        return vecs[0], u
