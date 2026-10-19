from __future__ import annotations

import io
from pathlib import Path

import pytest
import structlog

from agent import logging as alog
from agent.config import load_app, load_models
from agent.settings import REPO_ROOT, Settings


def test_models_yaml_has_every_role() -> None:
    models = load_models(REPO_ROOT / "config")
    for role in ("intake", "plan", "write_script", "fact_check_verdict", "tts", "embeddings", "transcribe"):
        assert models.role(role).model
    assert models.role("embeddings").dimensions == 768
    assert models.role("tts").voice == "Kore"


def test_unknown_role_is_a_clear_error() -> None:
    with pytest.raises(KeyError, match=r"models.yaml"):
        load_models(REPO_ROOT / "config").role("nope")


def test_app_config_languages_and_presets() -> None:
    app = load_app(REPO_ROOT / "config")
    assert set(app.languages) == {"ka", "en"}
    assert app.languages["ka"].tts_code == "ka-GE"
    assert app.presets["final"].width == 1080
    assert app.presets["preview"].fps == 15


def test_settings_ffmpeg_path(tmp_path: Path) -> None:
    s = Settings(ffmpeg_dir=tmp_path)
    assert s.ffmpeg("ffprobe") == tmp_path / "ffprobe"
    (tmp_path / "ffmpeg.exe").write_bytes(b"")
    assert s.ffmpeg() == tmp_path / "ffmpeg.exe"


def test_log_lines_carry_thread_id(monkeypatch: pytest.MonkeyPatch) -> None:
    buf = io.StringIO()
    alog.configure(json=True)
    structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=buf))
    with alog.bound_thread("proj-1"):
        alog.get_logger("t").info("hello", n=1)
    assert '"thread_id": "proj-1"' in buf.getvalue()
