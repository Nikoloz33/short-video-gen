"""google-genai backend on Vertex AI (Application Default Credentials — never API keys)."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

from google import genai
from google.genai import errors, types

from agent.llm.types import (
    Backend,
    GenRequest,
    GenResponse,
    RetryableError,
    TaskType,
    TokenUsage,
    TTSRequest,
    TTSResponse,
)

_RETRYABLE = {408, 429, 500, 502, 503, 504}


def _wrap(e: Exception) -> Exception:
    if isinstance(e, errors.APIError) and e.code in _RETRYABLE:
        return RetryableError(str(e), e.code)
    if isinstance(e, TimeoutError | ConnectionError):
        return RetryableError(str(e))
    return e


def _usage(meta: types.GenerateContentResponseUsageMetadata | None) -> TokenUsage:
    if meta is None:
        return TokenUsage()
    out = (meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0)
    audio = 0
    for d in meta.candidates_tokens_details or []:
        if d.modality == types.MediaModality.AUDIO:
            audio += d.token_count or 0
    return TokenUsage(in_tokens=meta.prompt_token_count or 0, out_tokens=out - audio, audio_out_tokens=audio)


class VertexBackend(Backend):
    def __init__(self, project: str, location: str) -> None:
        self._project = project
        self._location = location
        self._client: genai.Client | None = None
        self._lock = threading.Lock()

    @property
    def client(self) -> genai.Client:
        # One shared client, created lazily under a lock (embeddings run in a thread pool).
        with self._lock:
            if self._client is None:
                self._client = genai.Client(vertexai=True, project=self._project, location=self._location)
            return self._client

    def _contents(self, req: GenRequest) -> list[types.Content]:
        contents = [
            types.Content(role=t.role, parts=[types.Part.from_text(text=t.text)]) for t in req.history
        ]
        parts = [types.Part.from_bytes(data=a.data, mime_type=a.mime_type) for a in req.attachments]
        parts.append(types.Part.from_text(text=req.prompt))
        contents.append(types.Content(role="user", parts=parts))
        return contents

    def _config(self, req: GenRequest) -> types.GenerateContentConfig:
        kwargs: dict[str, Any] = {}
        if req.system:
            kwargs["system_instruction"] = req.system
        if req.temperature is not None:
            kwargs["temperature"] = req.temperature
        if req.thinking_level:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=req.thinking_level)
        if req.response_schema is not None:
            kwargs["response_mime_type"] = "application/json"
            kwargs["response_schema"] = req.response_schema
        return types.GenerateContentConfig(**kwargs)

    def generate(self, req: GenRequest) -> GenResponse:
        try:
            r = self.client.models.generate_content(
                model=req.model, contents=self._contents(req), config=self._config(req)
            )
        except Exception as e:
            raise _wrap(e) from e
        return GenResponse(text=r.text or "", usage=_usage(r.usage_metadata))

    def stream(self, req: GenRequest) -> Iterator[GenResponse]:
        try:
            for chunk in self.client.models.generate_content_stream(
                model=req.model, contents=self._contents(req), config=self._config(req)
            ):
                yield GenResponse(text=chunk.text or "", usage=_usage(chunk.usage_metadata))
        except Exception as e:
            raise _wrap(e) from e

    def tts(self, req: TTSRequest) -> TTSResponse:
        # Only the narration text: style instructions get read aloud, and system_instruction is a 400.
        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                language_code=req.language_code,
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=req.voice)
                ),
            ),
        )
        try:
            r = self.client.models.generate_content(model=req.model, contents=req.text, config=config)
        except Exception as e:
            raise _wrap(e) from e
        for cand in r.candidates or []:
            for part in (cand.content.parts if cand.content else None) or []:
                if part.inline_data and part.inline_data.data:
                    return TTSResponse(
                        data=part.inline_data.data,
                        mime_type=part.inline_data.mime_type or "audio/L16;rate=24000",
                        usage=_usage(r.usage_metadata),
                    )
        raise RetryableError("TTS response contained no audio")

    def embed(self, model: str, text: str, task_type: TaskType, dimensions: int) -> list[float]:
        try:
            r = self.client.models.embed_content(
                model=model,
                contents=text,
                config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=dimensions),
            )
        except Exception as e:
            raise _wrap(e) from e
        if not r.embeddings or not r.embeddings[0].values:
            raise RetryableError("embedding response was empty")
        return list(r.embeddings[0].values)
