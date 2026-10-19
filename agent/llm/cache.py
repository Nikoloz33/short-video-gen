"""Disk cache for model responses (dev/tests): identical requests return the stored response."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from agent.llm.types import GenRequest, GenResponse, TokenUsage


def request_key(req: GenRequest, role: str) -> str:
    payload = asdict(req)
    payload["attachments"] = [
        {"mime": a.mime_type, "sha": hashlib.sha256(a.data).hexdigest()} for a in req.attachments
    ]
    payload["role"] = role
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class DiskCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> GenResponse | None:
        p = self._path(key)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return GenResponse(text=data["text"], usage=TokenUsage(**data["usage"]))

    def put(self, key: str, resp: GenResponse) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"text": resp.text, "usage": asdict(resp.usage)}, ensure_ascii=False), "utf-8"
        )
        tmp.replace(p)
