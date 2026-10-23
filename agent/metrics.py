"""Operational metrics in data/metrics.db (next to the usage ledger): renders and narration checks."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.execute(
        "CREATE TABLE IF NOT EXISTS renders (ts REAL, project TEXT, version INTEGER, preset TEXT,"
        " video_s REAL, frames INTEGER, wall_ms INTEGER, render_ms INTEGER, encode_ms INTEGER,"
        " bundle_ms INTEGER, tts_cache_hits INTEGER, tts_synthesized INTEGER, ok INTEGER)"
    )
    return db


def record_render(path: Path, project: str, version: int, preset: str, video_s: float, result: dict[str, Any],
                  tts: dict[str, Any], ok: bool) -> None:  # fmt: skip
    stages = result.get("stages", {})
    with _connect(path) as db:
        db.execute(
            "INSERT INTO renders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                time.time(), project, version, preset, video_s, int(result.get("totalFrames", 0)),
                int(result.get("durationMs", 0)), int(stages.get("render_ms", 0)), int(stages.get("encode_ms", 0)),
                int(stages.get("bundle_ms", 0)), int(tts.get("cache_hits", 0)), int(tts.get("synthesized", 0)), int(ok),
            ),
        )  # fmt: skip


def renders(path: Path) -> list[dict[str, Any]]:
    with _connect(path) as db:
        db.row_factory = sqlite3.Row
        return [dict(r) for r in db.execute("SELECT * FROM renders ORDER BY ts")]


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)
