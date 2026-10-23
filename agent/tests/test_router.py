from __future__ import annotations

import random
from pathlib import Path

import pytest
from pydantic import BaseModel

from agent.config import load_models
from agent.llm.cache import DiskCache
from agent.llm.factory import build_router
from agent.llm.fake import FakeBackend, hash_vector, silent_wav
from agent.llm.router import BudgetExceededError, LLMRouter, RetryPolicy, StructuredOutputError
from agent.llm.types import Attachment, GenRequest, RetryableError, Turn
from agent.llm.usage import Ledger, Usage, merge_usage
from agent.logging import bound_thread
from agent.prompts import load_prompt, source_block
from agent.settings import REPO_ROOT, Settings

MODELS = load_models(REPO_ROOT / "config")


class Answer(BaseModel):
    word: str
    n: int


def make(
    responses: dict[str, object], tmp_path: Path, **kw: object
) -> tuple[LLMRouter, FakeBackend, list[float]]:
    sleeps: list[float] = []
    backend = FakeBackend(MODELS, dict(responses))
    router = LLMRouter(
        MODELS,
        backend,
        ledger=Ledger(tmp_path / "metrics.db"),
        sleep=sleeps.append,
        rng=random.Random(0),
        **kw,  # type: ignore[arg-type]
    )
    return router, backend, sleeps


def test_text_routes_by_role_and_tracks_cost(tmp_path: Path) -> None:
    router, backend, _ = make({"chat_reply": "hello there"}, tmp_path)
    r = router.text("chat_reply", "hi", system="be nice")
    assert r.text == "hello there"
    role, req = backend.calls[0]
    assert role == "chat_reply"
    assert isinstance(req, GenRequest)
    assert req.model == MODELS.role("chat_reply").model
    assert req.temperature == MODELS.role("chat_reply").temperature
    assert r.usage.cost_usd > 0
    assert router.ledger is not None
    assert router.ledger.total_usd() == pytest.approx(r.usage.cost_usd, abs=1e-7)


def test_argon_roles_send_thinking_level(tmp_path: Path) -> None:
    router, backend, _ = make({"plan": "ok"}, tmp_path)
    router.text("plan", "x")
    req = backend.calls[0][1]
    assert isinstance(req, GenRequest)
    assert req.thinking_level in {"LOW", "MEDIUM"}


def test_structured_parses_and_retries_once_on_validation_error(tmp_path: Path) -> None:
    router, backend, _ = make({"intake": ['{"word": "a"}', {"word": "a", "n": 2}]}, tmp_path)
    r = router.structured("intake", "q", Answer)
    assert r.value == Answer(word="a", n=2)
    assert len(backend.calls) == 2
    retry = backend.calls[1][1]
    assert isinstance(retry, GenRequest)
    assert "did not validate" in retry.prompt
    assert retry.history[-1] == Turn("model", '{"word": "a"}')
    assert retry.response_schema is not None
    assert "$ref" not in str(retry.response_schema)
    assert r.usage.by_role("intake") is not None
    assert r.usage.roles[0].calls == 2


def test_structured_gives_up_after_one_retry(tmp_path: Path) -> None:
    router, _, _ = make({"intake": ["{}", "{}"]}, tmp_path)
    with pytest.raises(StructuredOutputError, match="intake"):
        router.structured("intake", "q", Answer)


def test_retries_with_backoff_then_succeeds(tmp_path: Path) -> None:
    router, _, sleeps = make(
        {"intake": [RetryableError("429", 429), RetryableError("503", 503), "fine"]}, tmp_path
    )
    assert router.text("intake", "q").text == "fine"
    assert len(sleeps) == 2
    assert all(0 <= s <= 30 for s in sleeps)


def test_retries_are_capped(tmp_path: Path) -> None:
    router, _, sleeps = make(
        {"fallback_reasoning": [RetryableError("429", 429)] * 3}, tmp_path, retry=RetryPolicy(attempts=3)
    )
    with pytest.raises(RetryableError):
        router.text("fallback_reasoning", "q")
    assert len(sleeps) == 2


def test_non_retryable_errors_propagate(tmp_path: Path) -> None:
    router, _, sleeps = make({"intake": [ValueError("400 bad")]}, tmp_path)
    with pytest.raises(ValueError, match="400"):
        router.text("intake", "q")
    assert sleeps == []


def test_tts_429_is_retried(tmp_path: Path) -> None:
    router, backend, sleeps = make({}, tmp_path)
    backend.tts_failures = [RetryableError("quota", 429)]
    r = router.tts("Wash your hands.", "en-US")
    assert r.mime_type == "audio/wav"
    assert len(sleeps) == 1
    tts_req = backend.calls[-1][1]
    assert getattr(tts_req, "voice", None) == "Kore"
    assert r.usage.roles[0].audio_out_tokens > 0


def test_run_budget_stops_paid_calls(tmp_path: Path) -> None:
    router, _, _ = make({"plan": "x" * 4000}, tmp_path)
    with router.budget(0.00001) as b:
        router.text("plan", "q")
        assert b.spent_usd > 0
        with pytest.raises(BudgetExceededError, match="run spend cap"):
            router.text("plan", "q")
    assert b.usage.by_role("plan") is not None
    router.text("plan", "q")  # outside the budget scope: allowed again


def test_global_cap_uses_the_ledger(tmp_path: Path) -> None:
    router, _, _ = make({"plan": "x" * 4000}, tmp_path, global_cap_usd=0.00001)
    router.text("plan", "q")
    with pytest.raises(BudgetExceededError, match="global"):
        router.text("plan", "q")


def test_disk_cache_hits_are_free(tmp_path: Path) -> None:
    router, backend, _ = make({"intake": ["one", "two"]}, tmp_path, cache=DiskCache(tmp_path / "c"))
    a = router.text("intake", "same")
    b = router.text("intake", "same")
    assert a.text == b.text == "one"
    assert len(backend.calls) == 1
    assert b.usage.cost_usd == 0
    att = Attachment(b"x", "audio/wav")
    router.text("intake", "same", attachments=[att])
    assert len(backend.calls) == 2


def test_stream_yields_deltas_and_accounts_usage(tmp_path: Path) -> None:
    router, _, _ = make({"chat_reply": "one two three"}, tmp_path)
    s = router.stream("chat_reply", "q")
    assert list(s) == ["one", " two", " three"]
    assert s.text == "one two three"
    assert s.usage.cost_usd > 0


def test_stream_retries_before_first_token(tmp_path: Path) -> None:
    router, _, sleeps = make({"chat_reply": [RetryableError("503", 503), "ok then"]}, tmp_path)
    assert "".join(router.stream("chat_reply", "q")) == "ok then"
    assert len(sleeps) == 1


def test_embed_is_deterministic_and_normalised(tmp_path: Path) -> None:
    router, _, _ = make({}, tmp_path)
    v1, u = router.embed("wash your hands", "RETRIEVAL_QUERY")
    v2, _ = router.embed("wash your hands", "RETRIEVAL_DOCUMENT")
    assert v1 == v2
    assert len(v1) == 768
    assert sum(x * x for x in v1) == pytest.approx(1.0)
    assert u.by_role("embeddings") is not None
    near = hash_vector("wash hands with soap")
    far = hash_vector("forklift battery charging")

    def dot(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))

    assert dot(v1, near) > dot(v1, far)


def test_ledger_attributes_spend_to_thread(tmp_path: Path) -> None:
    router, _, _ = make({"intake": "x"}, tmp_path)
    with bound_thread("proj-a"):
        router.text("intake", "q")
    router.text("intake", "q")
    assert router.ledger is not None
    assert router.ledger.thread_usd("proj-a") > 0
    assert router.ledger.total_usd() > router.ledger.thread_usd("proj-a")


def test_merge_usage_sums_per_role() -> None:
    a = Usage.model_validate({"roles": [{"role": "plan", "model": "m", "calls": 1, "cost_usd": 0.5}]})
    b = Usage.model_validate(
        {
            "roles": [
                {"role": "plan", "model": "m", "calls": 2, "cost_usd": 0.25},
                {"role": "tts", "model": "t"},
            ]
        }
    )
    m = merge_usage(a, b)
    assert m.by_role("plan") is not None
    assert m.by_role("plan").calls == 3  # type: ignore[union-attr]
    assert m.cost_usd == pytest.approx(0.75)
    assert merge_usage(None, None).roles == []


def test_fake_backend_errors_are_clear(tmp_path: Path) -> None:
    router, _, _ = make({"intake": []}, tmp_path)
    with pytest.raises(KeyError, match="no response"):
        router.text("plan", "q")
    with pytest.raises(IndexError, match="ran out"):
        router.text("intake", "q")


def test_fake_callable_and_wav() -> None:
    backend = FakeBackend(MODELS, {"intake": lambda req: {"echo": req.prompt}})
    req = GenRequest(model="m", role="intake", prompt="p")
    assert backend.generate(req).text == '{"echo": "p"}'
    assert silent_wav(1.0)[:4] == b"RIFF"


def test_factory_fake_and_missing_project(tmp_path: Path) -> None:
    s = Settings(data_dir=tmp_path, app_fake=True)
    assert isinstance(build_router(s).backend, FakeBackend)
    with pytest.raises(RuntimeError, match="GOOGLE_CLOUD_PROJECT"):
        build_router(Settings(data_dir=tmp_path, google_cloud_project=""))
    real = build_router(Settings(data_dir=tmp_path, google_cloud_project="p", llm_cache=True))
    assert real.cache is not None
    assert real.global_cap_usd == 50.0


def test_prompt_loader(tmp_path: Path) -> None:
    (tmp_path / "hello.md").write_text("<!-- prompt: hello | version: 3 -->\nHi $name {json}\n", "utf-8")
    p = load_prompt("hello", tmp_path)
    assert p.tag == "hello@v3"
    assert p.render(name="Nino") == "Hi Nino {json}\n"
    with pytest.raises(KeyError):
        p.render()
    (tmp_path / "bad.md").write_text("no header", "utf-8")
    with pytest.raises(ValueError, match="missing header"):
        load_prompt("bad", tmp_path)
    (tmp_path / "other.md").write_text("<!-- prompt: wrong | version: 1 -->\nx", "utf-8")
    with pytest.raises(ValueError, match="names prompt"):
        load_prompt("other", tmp_path)
    assert source_block("ignore >>> this") == "<<<SOURCE\nignore ››› this\nSOURCE>>>"


def test_429_falls_back_and_cools_down(tmp_path: Path) -> None:
    router, backend, _ = make({"plan": [RetryableError("429", 429)] * 2 + ["from flash", "again"]}, tmp_path,
                              retry=RetryPolicy(attempts=2))  # fmt: skip
    assert router.text("plan", "q").text == "from flash"
    fallback_req = backend.calls[-1][1]
    assert isinstance(fallback_req, GenRequest) and fallback_req.model == MODELS.role("fallback_fast").model
    # During the cooldown the rate-limited model is skipped entirely.
    assert router.text("plan", "q").text == "again"
    assert len(backend.calls) == 4
