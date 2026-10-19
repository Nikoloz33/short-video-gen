"""FakeBackend for tests and APP_FAKE mode: responses keyed by role (value / list / callable)."""

from __future__ import annotations

import hashlib
import io
import math
import struct
import wave
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from agent.config import ModelsConfig
from agent.llm.types import (
    Backend,
    GenRequest,
    GenResponse,
    TaskType,
    TokenUsage,
    TTSRequest,
    TTSResponse,
)

Responder = str | BaseModel | dict[str, Any] | list[Any] | Callable[[GenRequest], Any] | Exception


def _render(value: Any) -> str:
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    if isinstance(value, dict | list):
        import json

        return json.dumps(value, ensure_ascii=False)
    return str(value)


def silent_wav(seconds: float, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return buf.getvalue()


def hash_vector(text: str, dims: int = 768) -> list[float]:
    """Deterministic bag-of-words embedding: shared words -> similar vectors (good enough for tests)."""
    vec = [0.0] * dims
    for word in text.lower().split():
        word = word.strip(".,;:!?()\"'")
        if not word:
            continue
        h = int.from_bytes(hashlib.sha256(word.encode("utf-8")).digest()[:8], "big")
        vec[h % dims] += 1.0 if (h >> 32) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


@dataclass
class FakeBackend(Backend):
    """`responses[role]`: a value (always), a list (one per call, in order), a callable(request) or an
    Exception instance (raised). Tests address roles, never model names."""

    models: ModelsConfig
    responses: dict[str, Any] = field(default_factory=dict)
    tts_chars_per_sec: float = 14.0
    tts_failures: list[Exception] = field(default_factory=list)
    calls: list[tuple[str, GenRequest | TTSRequest | str]] = field(default_factory=list)

    def _next(self, role: str, req: GenRequest) -> str:
        if role not in self.responses:
            raise KeyError(f"FakeBackend has no response for role {role!r}")
        r = self.responses[role]
        if isinstance(r, list):
            if not r:
                raise IndexError(f"FakeBackend ran out of responses for role {role!r}")
            r = r.pop(0)
        if isinstance(r, Exception):
            raise r
        if callable(r) and not isinstance(r, BaseModel):
            r = r(req)
        return _render(r)

    def generate(self, req: GenRequest) -> GenResponse:
        role = req.role
        self.calls.append((role, req))
        text = self._next(role, req)
        usage = TokenUsage(in_tokens=max(1, len(req.prompt) // 4), out_tokens=max(1, len(text) // 4))
        return GenResponse(text=text, usage=usage)

    def stream(self, req: GenRequest) -> Iterator[GenResponse]:
        resp = self.generate(req)
        words = resp.text.split(" ")
        for i, w in enumerate(words):
            yield GenResponse(text=w if i == 0 else f" {w}")
        yield GenResponse(text="", usage=resp.usage)

    def tts(self, req: TTSRequest) -> TTSResponse:
        self.calls.append(("tts", req))
        if self.tts_failures:
            raise self.tts_failures.pop(0)
        seconds = max(0.4, len(req.text) / self.tts_chars_per_sec)
        return TTSResponse(
            data=silent_wav(seconds),
            mime_type="audio/wav",
            usage=TokenUsage(audio_out_tokens=int(seconds * 25)),
        )

    def embed(self, model: str, text: str, task_type: TaskType, dimensions: int) -> list[float]:
        self.calls.append(("embeddings", text))
        return hash_vector(text, dimensions)


def pcm_tone(seconds: float, rate: int = 24000, freq: float = 220.0) -> bytes:
    """Raw 16-bit mono PCM (what Gemini TTS returns as audio/L16)."""
    n = int(seconds * rate)
    return b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / rate))) for i in range(n))
