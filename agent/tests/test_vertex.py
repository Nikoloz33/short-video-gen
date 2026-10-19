"""VertexBackend against a stub client built from real google-genai types (no network)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from google.genai import errors, types

from agent.llm.types import Attachment, GenRequest, RetryableError, TTSRequest, Turn
from agent.llm.vertex import VertexBackend


def _resp(parts: list[types.Part], audio_tokens: int = 0) -> types.GenerateContentResponse:
    details = [types.ModalityTokenCount(modality=types.MediaModality.AUDIO, token_count=audio_tokens)]
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=parts))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=10,
            candidates_token_count=5 + audio_tokens,
            thoughts_token_count=3,
            candidates_tokens_details=details if audio_tokens else None,
        ),
    )


class StubModels:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.raise_: Exception | None = None
        self.reply: types.GenerateContentResponse = _resp([types.Part.from_text(text="hello")])

    def generate_content(self, **kw: Any) -> types.GenerateContentResponse:
        self.calls.append(kw)
        if self.raise_:
            raise self.raise_
        return self.reply

    def generate_content_stream(self, **kw: Any) -> Iterator[types.GenerateContentResponse]:
        self.calls.append(kw)
        if self.raise_:
            raise self.raise_
        yield _resp([types.Part.from_text(text="a")])
        yield _resp([types.Part.from_text(text="b")])

    def embed_content(self, **kw: Any) -> types.EmbedContentResponse:
        self.calls.append(kw)
        if self.raise_:
            raise self.raise_
        return types.EmbedContentResponse(embeddings=[types.ContentEmbedding(values=[0.1, 0.2])])


class StubClient:
    def __init__(self) -> None:
        self.models = StubModels()


@pytest.fixture
def backend() -> tuple[VertexBackend, StubModels]:
    b = VertexBackend("proj", "eu")
    stub = StubClient()
    b._client = stub  # type: ignore[assignment]
    return b, stub.models


def test_generate_builds_contents_and_config(backend: tuple[VertexBackend, StubModels]) -> None:
    b, models = backend
    req = GenRequest(
        model="m",
        role="plan",
        prompt="p",
        system="sys",
        history=(Turn("user", "u0"), Turn("model", "m0")),
        attachments=(Attachment(b"RIFF", "audio/wav"),),
        temperature=0.2,
        thinking_level="LOW",
        response_schema={"type": "object", "properties": {"a": {"type": "string"}}},
    )
    r = b.generate(req)
    assert r.text == "hello"
    assert r.usage.in_tokens == 10
    assert r.usage.out_tokens == 8  # candidates + thoughts
    kw = models.calls[0]
    contents = kw["contents"]
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert contents[-1].parts[0].inline_data.mime_type == "audio/wav"
    cfg = kw["config"]
    assert cfg.system_instruction == "sys"
    assert cfg.response_mime_type == "application/json"
    assert cfg.thinking_config.thinking_level is not None


def test_stream(backend: tuple[VertexBackend, StubModels]) -> None:
    b, _ = backend
    out = list(b.stream(GenRequest(model="m", role="chat_reply", prompt="p")))
    assert [c.text for c in out] == ["a", "b"]


def test_tts_returns_inline_audio_and_audio_tokens(backend: tuple[VertexBackend, StubModels]) -> None:
    b, models = backend
    blob = types.Part(inline_data=types.Blob(data=b"PCM", mime_type="audio/L16;rate=24000"))
    models.reply = _resp([blob], audio_tokens=50)
    r = b.tts(TTSRequest(model="t", text="Wash.", voice="Kore", language_code="ka-GE"))
    assert r.data == b"PCM"
    assert r.mime_type.startswith("audio/L16")
    assert r.usage.audio_out_tokens == 50
    cfg = models.calls[0]["config"]
    assert cfg.system_instruction is None  # rejected by the TTS model
    assert cfg.speech_config.language_code == "ka-GE"
    assert models.calls[0]["contents"] == "Wash."  # only the narration text


def test_tts_without_audio_is_retryable(backend: tuple[VertexBackend, StubModels]) -> None:
    b, models = backend
    models.reply = _resp([types.Part.from_text(text="no audio")])
    with pytest.raises(RetryableError):
        b.tts(TTSRequest(model="t", text="x", voice="Kore", language_code="en-US"))


def test_embed(backend: tuple[VertexBackend, StubModels]) -> None:
    b, models = backend
    assert b.embed("e", "hi", "RETRIEVAL_QUERY", 768) == [0.1, 0.2]
    assert models.calls[0]["config"].task_type == "RETRIEVAL_QUERY"
    models.raise_ = None
    models.calls.clear()


@pytest.mark.parametrize(("code", "retryable"), [(429, True), (503, True), (400, False)])
def test_error_classification(backend: tuple[VertexBackend, StubModels], code: int, retryable: bool) -> None:
    b, models = backend
    models.raise_ = errors.APIError(code, {"error": {"message": "boom", "status": "X"}})
    exc = RetryableError if retryable else errors.APIError
    with pytest.raises(exc):
        b.generate(GenRequest(model="m", role="intake", prompt="p"))
    with pytest.raises(exc):
        list(b.stream(GenRequest(model="m", role="intake", prompt="p")))
    with pytest.raises(exc):
        b.embed("e", "x", "RETRIEVAL_QUERY", 8)
    with pytest.raises(exc):
        b.tts(TTSRequest(model="t", text="x", voice="Kore", language_code="en-US"))


def test_timeouts_are_retryable(backend: tuple[VertexBackend, StubModels]) -> None:
    b, models = backend
    models.raise_ = TimeoutError("slow")
    with pytest.raises(RetryableError):
        b.generate(GenRequest(model="m", role="intake", prompt="p"))


def test_client_is_created_lazily_once() -> None:
    b = VertexBackend("proj", "eu")
    assert b._client is None
