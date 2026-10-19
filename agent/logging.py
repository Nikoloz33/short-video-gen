"""structlog setup. Every log line carries the bound `thread_id` (contextvars); never use print."""

from __future__ import annotations

import contextvars
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog


def configure(level: str = "INFO", json: bool = False) -> None:
    """Idempotent logging setup for CLIs, the API and tests."""
    # Windows consoles default to cp1252; Georgian text would crash the stream handler.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    renderer: Any = (
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level.upper()]),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


_thread_id: contextvars.ContextVar[str] = contextvars.ContextVar("thread_id", default="-")


def current_thread_id() -> str:
    """The project thread the current code runs for ('-' outside a run); used by the usage ledger."""
    return _thread_id.get()


@contextmanager
def bound_thread(thread_id: str) -> Iterator[None]:
    """Bind `thread_id` to every log line (and usage record) emitted inside the block."""
    token = _thread_id.set(thread_id)
    try:
        with structlog.contextvars.bound_contextvars(thread_id=thread_id):
            yield
    finally:
        _thread_id.reset(token)
