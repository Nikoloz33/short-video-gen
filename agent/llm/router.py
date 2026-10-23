"""The one place model calls happen.

- Roles come from config/models.yaml; code never names a model.
- Retries with exponential backoff + full jitter on retryable errors (429/5xx/timeouts, TTS included).
- Optional disk cache (dev/tests), usage + cost per call, a per-run budget and a global spend cap.
- Structured output: Gemini JSON mode with a flattened schema, parsed into Pydantic with ONE
  validation retry that shows the model its errors.
"""

from __future__ import annotations

import contextvars
import random
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from agent.config import ModelsConfig
from agent.llm.cache import DiskCache, request_key
from agent.llm.types import (
    Attachment,
    Backend,
    GenRequest,
    GenResponse,
    RetryableError,
    TaskType,
    TokenUsage,
    TTSRequest,
    TTSResponse,
    Turn,
)
from agent.llm.usage import Ledger, Usage, cost_of, merge_usage, single
from agent.logging import current_thread_id, get_logger
from agent.schemas.gemini import gemini_schema

log = get_logger("llm")
T = TypeVar("T", bound=BaseModel)
T_co = TypeVar("T_co")


class BudgetExceededError(RuntimeError):
    """The run (or the global ledger) reached its spend cap; no further paid calls are made."""


class StructuredOutputError(RuntimeError):
    def __init__(self, role: str, errors: str) -> None:
        super().__init__(f"{role}: model output did not match the schema after a retry:\n{errors}")
        self.role = role
        self.errors = errors


@dataclass
class RunBudget:
    cap_usd: float
    spent_usd: float = 0.0
    usage: Usage = field(default_factory=Usage)


_run_budget: contextvars.ContextVar[RunBudget | None] = contextvars.ContextVar("run_budget", default=None)


@dataclass
class Result[T: BaseModel]:
    value: T
    usage: Usage


@dataclass
class TextResult:
    text: str
    usage: Usage


@dataclass
class TTSResult:
    data: bytes
    mime_type: str
    usage: Usage


class StreamResult:
    """Iterate for text deltas; `.text` and `.usage` are complete once iteration ends."""

    def __init__(self, it: Iterator[str]) -> None:
        self._it = it
        self.text = ""
        self.usage = Usage()

    def __iter__(self) -> Iterator[str]:
        for delta in self._it:
            self.text += delta
            yield delta


@dataclass
class RetryPolicy:
    attempts: int = 6
    base_s: float = 2.0
    cap_s: float = 60.0


class LLMRouter:
    def __init__(
        self,
        models: ModelsConfig,
        backend: Backend,
        *,
        ledger: Ledger | None = None,
        cache: DiskCache | None = None,
        global_cap_usd: float | None = None,
        retry: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self.models = models
        self.backend = backend
        self.ledger = ledger
        self.cache = cache
        self.global_cap_usd = global_cap_usd
        self.retry = retry or RetryPolicy()
        self._sleep = sleep
        self._rng = rng or random.Random()
        #: model -> monotonic time until which it is skipped (it kept returning 429).
        self._cooldown: dict[str, float] = {}
        self.cooldown_s = 300.0

    # ---- budget ---------------------------------------------------------------------------------
    @contextmanager
    def budget(self, cap_usd: float) -> Iterator[RunBudget]:
        """Per-run spend cap for everything called inside the block (threads included)."""
        b = RunBudget(cap_usd=cap_usd)
        token = _run_budget.set(b)
        try:
            yield b
        finally:
            _run_budget.reset(token)

    def _check_budget(self) -> None:
        b = _run_budget.get()
        if b is not None and b.spent_usd >= b.cap_usd:
            raise BudgetExceededError(f"run spend cap reached (${b.spent_usd:.4f} of ${b.cap_usd:.2f})")
        if self.global_cap_usd is not None and self.ledger is not None:
            total = self.ledger.total_usd()
            if total >= self.global_cap_usd:
                raise BudgetExceededError(
                    f"global spend cap reached (${total:.2f} of ${self.global_cap_usd:.2f})"
                )

    def _account(self, role: str, model: str, usage: TokenUsage, cached: bool = False) -> Usage:
        cfg = self.models.role(role)
        cost = 0.0 if cached else cost_of(cfg, usage)
        if self.ledger is not None:
            self.ledger.record(current_thread_id(), role, model, usage, cost, cached=cached)
        u = single(role, model, usage, cost)
        b = _run_budget.get()
        if b is not None:
            b.spent_usd += cost
            b.usage = merge_usage(b.usage, u)
        return u

    # ---- retries --------------------------------------------------------------------------------
    def _with_retry(self, role: str, fn: Callable[[], T_co], attempts: int | None = None) -> T_co:
        n = attempts or self.retry.attempts
        for i in range(n):
            try:
                return fn()
            except RetryableError as e:
                if i == n - 1:
                    raise
                delay = self._rng.uniform(0, min(self.retry.cap_s, self.retry.base_s * 2**i))
                log.warning("retrying", role=role, attempt=i + 1, status=e.status, delay_s=round(delay, 2))
                self._sleep(delay)
        raise AssertionError("unreachable")  # pragma: no cover

    # ---- requests -------------------------------------------------------------------------------
    def _request(
        self,
        role: str,
        prompt: str,
        system: str | None,
        history: Sequence[Turn],
        attachments: Sequence[Attachment],
        schema: dict[str, object] | None,
    ) -> GenRequest:
        cfg = self.models.role(role)
        return GenRequest(
            model=cfg.model,
            role=role,
            prompt=prompt,
            system=system,
            history=tuple(history),
            attachments=tuple(attachments),
            temperature=cfg.temperature,
            thinking_level=cfg.thinking_level,
            response_schema=dict(schema) if schema is not None else None,
        )

    def _generate(self, role: str, req: GenRequest) -> tuple[GenResponse, Usage]:
        key = request_key(req, role) if self.cache else None
        if self.cache and key:
            hit = self.cache.get(key)
            if hit is not None:
                log.debug("cache hit", role=role)
                return hit, self._account(role, req.model, hit.usage, cached=True)
        self._check_budget()
        t0 = time.perf_counter()
        fb = self.models.role(role).fallback
        cooling = fb is not None and self._cooldown.get(req.model, 0.0) > time.monotonic()
        try:
            if cooling:
                raise RetryableError("model cooling down after repeated 429s", 429)
            resp = self._with_retry(role, lambda: self.backend.generate(req))
        except RetryableError as e:
            if e.status != 429 or not fb:
                raise
            if not cooling:
                self._cooldown[req.model] = time.monotonic() + self.cooldown_s
            # Rate-limited model: run the same request on the fallback role's model.
            fcfg = self.models.role(fb)
            log.warning("falling back", role=role, to=fb, model=fcfg.model)
            req = replace(
                req, model=fcfg.model, thinking_level=fcfg.thinking_level, temperature=fcfg.temperature
            )
            resp = self._with_retry(fb, lambda: self.backend.generate(req))
            return resp, self._account(fb, req.model, resp.usage)
        log.info("llm call", role=role, model=req.model, ms=round((time.perf_counter() - t0) * 1000))
        if self.cache and key:
            self.cache.put(key, resp)
        return resp, self._account(role, req.model, resp.usage)

    def text(
        self,
        role: str,
        prompt: str,
        *,
        system: str | None = None,
        history: Sequence[Turn] = (),
        attachments: Sequence[Attachment] = (),
    ) -> TextResult:
        resp, usage = self._generate(role, self._request(role, prompt, system, history, attachments, None))
        return TextResult(text=resp.text, usage=usage)

    def structured(
        self,
        role: str,
        prompt: str,
        schema: type[T],
        *,
        system: str | None = None,
        history: Sequence[Turn] = (),
        attachments: Sequence[Attachment] = (),
    ) -> Result[T]:
        json_schema = gemini_schema(schema)
        req = self._request(role, prompt, system, history, attachments, json_schema)
        resp, usage = self._generate(role, req)
        try:
            return Result(schema.model_validate_json(resp.text), usage)
        except ValidationError as e:
            errors = str(e)
            log.warning("structured output invalid, retrying once", role=role, errors=errors[:500])
        retry_history = (*history, Turn("user", prompt), Turn("model", resp.text))
        fix = (
            "Your previous JSON did not validate against the schema. Errors:\n"
            f"{errors}\nReturn the corrected JSON only."
        )
        req2 = self._request(role, fix, system, retry_history, attachments, json_schema)
        resp2, usage2 = self._generate(role, req2)
        total = merge_usage(usage, usage2)
        try:
            return Result(schema.model_validate_json(resp2.text), total)
        except ValidationError as e:
            raise StructuredOutputError(role, str(e)) from e

    def stream(
        self, role: str, prompt: str, *, system: str | None = None, history: Sequence[Turn] = ()
    ) -> StreamResult:
        req = self._request(role, prompt, system, history, (), None)
        self._check_budget()

        def run() -> Iterator[str]:
            usage = TokenUsage()
            # Retry only before the first token: a half-streamed reply cannot be retried silently.
            chunks = self._with_retry(role, lambda: _prime(self.backend.stream(req)))
            for chunk in chunks:
                if chunk.usage.in_tokens or chunk.usage.out_tokens:
                    usage = chunk.usage
                if chunk.text:
                    yield chunk.text
            result.usage = self._account(role, req.model, usage)

        result = StreamResult(run())
        return result

    def tts(self, text: str, language_code: str, voice: str | None = None) -> TTSResult:
        cfg = self.models.role("tts")
        req = TTSRequest(
            model=cfg.model, text=text, voice=voice or cfg.voice or "Kore", language_code=language_code
        )
        self._check_budget()
        # TTS quota is low per minute: allow more patient retries.
        resp: TTSResponse = self._with_retry(
            "tts", lambda: self.backend.tts(req), attempts=self.retry.attempts + 3
        )
        return TTSResult(
            data=resp.data, mime_type=resp.mime_type, usage=self._account("tts", cfg.model, resp.usage)
        )

    def embed(self, text: str, task_type: TaskType) -> tuple[list[float], Usage]:
        cfg = self.models.role("embeddings")
        self._check_budget()
        vec = self._with_retry(
            "embeddings", lambda: self.backend.embed(cfg.model, text, task_type, cfg.dimensions or 768)
        )
        # The embeddings API reports no token counts: estimate ~4 characters per token for cost.
        usage = TokenUsage(in_tokens=max(1, len(text) // 4))
        return vec, self._account("embeddings", cfg.model, usage)


def _prime(it: Iterator[GenResponse]) -> Iterator[GenResponse]:
    """Pull the first chunk eagerly so connection errors surface inside the retry loop."""
    first = next(it, None)

    def chain() -> Iterator[GenResponse]:
        if first is not None:
            yield first
        yield from it

    return chain()
