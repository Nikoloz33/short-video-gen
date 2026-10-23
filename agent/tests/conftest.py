from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from agent.config import load_models
from agent.graph.runner import Runner, build_deps
from agent.llm.fake import FakeBackend
from agent.llm.fake_scenario import scenario_responses
from agent.llm.router import LLMRouter
from agent.llm.usage import Ledger
from agent.settings import REPO_ROOT, Settings

SOURCES = REPO_ROOT / "data" / "fixtures" / "sources"


@pytest.fixture(autouse=True)
def _quiet_logs() -> None:
    from agent.logging import configure

    configure(level="WARNING")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", app_fake=True, app_token="t", max_run_cost_usd=5.0)


@pytest.fixture
def router(tmp_path: Path) -> LLMRouter:
    models = load_models(REPO_ROOT / "config")
    return LLMRouter(models, FakeBackend(models, scenario_responses()), ledger=Ledger(tmp_path / "m.db"),
                     sleep=lambda _s: None)  # fmt: skip


def make_runner(settings: Settings, responses: dict[str, Any] | None = None) -> Runner:
    return Runner(build_deps(settings, responses if responses is not None else scenario_responses()))


@pytest.fixture
def runner(settings: Settings) -> Iterator[Runner]:
    r = make_runner(settings)
    yield r
    r.close()


def new_project(r: Runner, source: str = "handwashing-sop-en.md") -> str:
    pid = r.deps.projects.create("t")
    r.deps.projects.add_source(pid, source, (SOURCES / source).read_bytes(), r.deps.router)
    return pid


def events(it: Any) -> list[dict[str, Any]]:
    return list(it)


def types(evs: list[dict[str, Any]]) -> list[str]:
    return [e["type"] for e in evs]


def nodes(evs: list[dict[str, Any]]) -> list[str]:
    return [e["node"] for e in evs if e["type"] == "node"]
