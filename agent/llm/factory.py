"""Builds the router for the current settings: Vertex + ledger in production, fakes when asked."""

from __future__ import annotations

from typing import Any

from agent.config import load_models
from agent.llm.cache import DiskCache
from agent.llm.fake import FakeBackend
from agent.llm.router import LLMRouter
from agent.llm.usage import Ledger
from agent.llm.vertex import VertexBackend
from agent.settings import Settings, get_settings


def build_router(settings: Settings | None = None, fake_responses: dict[str, Any] | None = None) -> LLMRouter:
    s = settings or get_settings()
    models = load_models(s.config_dir)
    if s.app_fake or fake_responses is not None:
        # Fake spend goes to its own ledger so it never counts against the real budget.
        fake_ledger = Ledger(s.data_dir / "metrics-fake.db")
        return LLMRouter(models, FakeBackend(models, fake_responses or {}), ledger=fake_ledger)
    ledger = Ledger(s.data_dir / "metrics.db")
    if not s.google_cloud_project:
        raise RuntimeError(
            "GOOGLE_CLOUD_PROJECT is not set (.env); run `gcloud auth application-default login`"
        )
    return LLMRouter(
        models,
        VertexBackend(s.google_cloud_project, s.google_cloud_location or models.location),
        ledger=ledger,
        cache=DiskCache(s.data_dir / "cache" / "llm") if s.llm_cache else None,
        global_cap_usd=s.max_total_spend_usd,
    )
