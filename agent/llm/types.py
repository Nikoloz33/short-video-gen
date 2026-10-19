"""Backend-neutral request/response types for the router."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

TaskType = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]


@dataclass(frozen=True)
class Attachment:
    """Inline binary input (e.g. a WAV clip to transcribe)."""

    data: bytes
    mime_type: str


@dataclass(frozen=True)
class Turn:
    role: Literal["user", "model"]
    text: str


@dataclass(frozen=True)
class GenRequest:
    model: str
    #: The router role (metadata for logs, cache keys and fakes; not sent to the provider).
    role: str
    prompt: str
    system: str | None = None
    history: tuple[Turn, ...] = ()
    attachments: tuple[Attachment, ...] = ()
    temperature: float | None = None
    thinking_level: str | None = None
    response_schema: dict[str, Any] | None = None


@dataclass
class TokenUsage:
    in_tokens: int = 0
    out_tokens: int = 0
    audio_out_tokens: int = 0


@dataclass
class GenResponse:
    text: str
    usage: TokenUsage = field(default_factory=TokenUsage)


@dataclass(frozen=True)
class TTSRequest:
    model: str
    text: str
    voice: str
    language_code: str


@dataclass
class TTSResponse:
    data: bytes
    mime_type: str
    usage: TokenUsage = field(default_factory=TokenUsage)


class Backend(Protocol):
    """What the router needs from a model provider (Vertex in production, fakes in tests)."""

    def generate(self, req: GenRequest) -> GenResponse: ...

    def stream(self, req: GenRequest) -> Iterator[GenResponse]:
        """Yields text deltas; the last item may carry the usage (text may be empty)."""
        ...

    def tts(self, req: TTSRequest) -> TTSResponse: ...

    def embed(self, model: str, text: str, task_type: TaskType, dimensions: int) -> list[float]: ...


class RetryableError(Exception):
    """A transient provider failure (429 / 5xx / timeouts): the router retries with backoff."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status
