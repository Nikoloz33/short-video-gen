"""Runs the graph for a project thread and turns LangGraph streams into UI events.

Events (dicts with `type`): token, card, status, render_progress, render_done, fact_progress,
node, awaiting_review, error, done. One run = one user message or one review answer.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command, StreamMode

from agent.graph.build import build_graph
from agent.graph.deps import Deps
from agent.llm.factory import build_router
from agent.llm.router import BudgetExceededError
from agent.logging import bound_thread, get_logger
from agent.render.worker import FakeRenderer, RenderWorker
from agent.settings import REPO_ROOT, Settings
from agent.storage import ProjectStore
from agent.tts.narrator import Narrator

log = get_logger("runner")
STREAM_MODES: list[StreamMode] = ["updates", "custom"]


def build_deps(settings: Settings, fake_responses: dict[str, Any] | None = None) -> Deps:
    fake = settings.app_fake or fake_responses is not None
    if fake and fake_responses is None:
        from agent.llm.fake_scenario import scenario_responses

        fake_responses = scenario_responses()
    router = build_router(settings, fake_responses if fake else None)
    renderer = FakeRenderer(settings.ffmpeg()) if fake else RenderWorker(REPO_ROOT)
    narrator = Narrator(router, settings.data_dir / "cache" / "tts", settings.ffmpeg(), verify=not fake)
    return Deps(settings=settings, router=router, projects=ProjectStore(settings.data_dir), renderer=renderer,
                narrator=narrator)  # fmt: skip


class Runner:
    def __init__(self, deps: Deps, checkpoint_db: Path | None = None) -> None:
        self.deps = deps
        path = checkpoint_db or deps.settings.data_dir / "checkpoints.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self.saver = SqliteSaver(self._conn)
        self.graph = build_graph(deps, self.saver)
        self._locks: dict[str, threading.Lock] = {}

    def close(self) -> None:
        self._conn.close()

    def config(self, project_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": project_id}, "recursion_limit": self.deps.app.recursion_limit}

    def lock(self, project_id: str) -> threading.Lock:
        return self._locks.setdefault(project_id, threading.Lock())

    def pending_interrupt(self, project_id: str) -> dict[str, Any] | None:
        snap = self.graph.get_state(self.config(project_id))
        for task in snap.tasks:
            for intr in task.interrupts:
                value: dict[str, Any] = dict(intr.value)
                return value
        return None

    def state(self, project_id: str) -> dict[str, Any]:
        values: dict[str, Any] = self.graph.get_state(self.config(project_id)).values
        return values

    def can_retry(self, project_id: str) -> bool:
        """A run that died on an error (e.g. a provider 429) left pending tasks in the checkpoint."""
        snap = self.graph.get_state(self.config(project_id))
        return bool(snap.next) and self.pending_interrupt(project_id) is None

    def run(
        self,
        project_id: str,
        message: str | None = None,
        resume: dict[str, Any] | None = None,
        retry: bool = False,
    ) -> Iterator[dict[str, Any]]:
        """Streams events. A free-text message while a review is pending resumes it as an edit."""
        if message is not None and resume is None and self.pending_interrupt(project_id):
            resume = {"action": "edit", "text": message}
        inp: Any
        if retry:
            inp = None  # continue from the last checkpoint: completed nodes are not redone
        elif resume is not None:
            inp = Command(resume=resume)
        else:
            inp = {"messages": [HumanMessage(content=message or "")], "project_id": project_id}
        with bound_thread(project_id), self.deps.router.budget(self.deps.settings.max_run_cost_usd) as budget:
            try:
                for mode, chunk in self.graph.stream(inp, self.config(project_id), stream_mode=STREAM_MODES):
                    if mode == "custom":
                        yield cast(dict[str, Any], chunk)
                    elif isinstance(chunk, dict):
                        for node, update in chunk.items():
                            if node == "__interrupt__":
                                for intr in update:
                                    yield {"type": "awaiting_review", **dict(intr.value)}
                            else:
                                yield {"type": "node", "node": node}
            except BudgetExceededError as e:
                log.warning("budget exceeded", error=str(e))
                yield {"type": "error", "code": "budget", "message": str(e)}
            except Exception as e:
                log.exception("run failed")
                yield {"type": "error", "code": "run_failed", "message": str(e)}
            values = self.state(project_id)
            yield {
                "type": "done",
                "status": values.get("status", "idle"),
                "can_retry": self.can_retry(project_id),
                "run_cost_usd": round(budget.spent_usd, 6),
                "total_cost_usd": round(
                    sum(r.get("cost_usd", 0) for r in (values.get("usage") or {}).get("roles", [])), 6
                ),
            }
