"""Read-only access to the video project's catalogs (icons) — the agent validates against the same
files the templates render from."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

from agent.settings import get_settings


class IconTags(TypedDict):
    en: list[str]
    ka: list[str]


class IconEntry(TypedDict, total=False):
    name: str
    lucide: str
    custom: bool
    tags: IconTags


def catalog_dir() -> Path:
    return get_settings().video_dir / "src" / "catalog"


@lru_cache(maxsize=1)
def icons() -> tuple[IconEntry, ...]:
    data = json.loads((catalog_dir() / "icons.json").read_text(encoding="utf-8"))
    entries: list[IconEntry] = data["icons"]
    return tuple(entries)


@lru_cache(maxsize=1)
def icon_names() -> frozenset[str]:
    return frozenset(i["name"] for i in icons())


def icon_prompt_list() -> str:
    """Compact catalog for prompts: `name: tag, tag` per line (English tags only, to save tokens)."""
    return "\n".join(f"{i['name']}: {', '.join(i['tags']['en'])}" for i in icons())


def search_icons(query: str) -> list[str]:
    q = query.strip().lower()
    if not q:
        return []
    scored: list[tuple[int, str]] = []
    for i in icons():
        tags = [t.lower() for t in (*i["tags"]["en"], *i["tags"]["ka"])]
        name = i["name"]
        score = 3 if name == q else 2 if q in tags else 1 if (any(q in t for t in tags) or q in name) else 0
        if score:
            scored.append((score, name))
    return [n for _, n in sorted(scored, key=lambda x: -x[0])]
