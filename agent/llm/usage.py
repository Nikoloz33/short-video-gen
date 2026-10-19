"""Usage + cost accounting: per-run totals (state reducer) and a persistent ledger (metrics.db)."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from pydantic import BaseModel, Field

from agent.config import ModelRole
from agent.llm.types import TokenUsage


class RoleUsage(BaseModel):
    """Totals for one role (lists of objects, not dict maps: the state stays Gemini/JSON friendly)."""

    role: str
    model: str
    calls: int = 0
    in_tokens: int = 0
    out_tokens: int = 0
    audio_out_tokens: int = 0
    cost_usd: float = 0.0


class Usage(BaseModel):
    roles: list[RoleUsage] = Field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        return round(sum(r.cost_usd for r in self.roles), 8)

    def by_role(self, role: str) -> RoleUsage | None:
        return next((r for r in self.roles if r.role == role), None)


def cost_of(cfg: ModelRole, usage: TokenUsage) -> float:
    p = cfg.pricing
    return (
        usage.in_tokens * p.in_per_m
        + usage.out_tokens * p.out_per_m
        + usage.audio_out_tokens * p.audio_out_per_m
    ) / 1_000_000


def merge_usage(a: Usage | None, b: Usage | None) -> Usage:
    """LangGraph reducer: sums per-role totals."""
    out: dict[tuple[str, str], RoleUsage] = {}
    for u in (a, b):
        for r in u.roles if u else []:
            key = (r.role, r.model)
            cur = out.get(key)
            if cur is None:
                out[key] = r.model_copy()
            else:
                cur.calls += r.calls
                cur.in_tokens += r.in_tokens
                cur.out_tokens += r.out_tokens
                cur.audio_out_tokens += r.audio_out_tokens
                cur.cost_usd = round(cur.cost_usd + r.cost_usd, 8)
    return Usage(roles=sorted(out.values(), key=lambda r: r.role))


def single(role: str, model: str, usage: TokenUsage, cost: float) -> Usage:
    return Usage(
        roles=[
            RoleUsage(
                role=role,
                model=model,
                calls=1,
                in_tokens=usage.in_tokens,
                out_tokens=usage.out_tokens,
                audio_out_tokens=usage.audio_out_tokens,
                cost_usd=round(cost, 8),
            )
        ]
    )


class Ledger:
    """Append-only record of every billed call. `total_usd()` backs the global spend cap."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._lock = threading.Lock()
        with self._connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS usage (ts REAL, thread_id TEXT, role TEXT, model TEXT,"
                " in_tokens INTEGER, out_tokens INTEGER, audio_out_tokens INTEGER,"
                " cost_usd REAL, cached INTEGER)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=10)

    def record(
        self, thread_id: str, role: str, model: str, usage: TokenUsage, cost: float, cached: bool = False
    ) -> None:
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO usage VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    time.time(),
                    thread_id,
                    role,
                    model,
                    usage.in_tokens,
                    usage.out_tokens,
                    usage.audio_out_tokens,
                    0.0 if cached else cost,
                    int(cached),
                ),
            )

    def total_usd(self) -> float:
        with self._connect() as db:
            row = db.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM usage").fetchone()
        return float(row[0])

    def thread_usd(self, thread_id: str) -> float:
        with self._connect() as db:
            row = db.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM usage WHERE thread_id = ?", (thread_id,)
            ).fetchone()
        return float(row[0])
