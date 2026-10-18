"""Environment settings (.env). Model names never live here — see config/models.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    google_cloud_project: str = ""
    google_cloud_location: str = "eu"
    google_genai_use_vertexai: bool = True
    ffmpeg_dir: Path = Path(r"C:\ffmpeg-7.1.1-essentials_build\bin")
    app_token: str = "dev-token"
    max_run_cost_usd: float = Field(default=2.0, gt=0)
    data_dir: Path = REPO_ROOT / "data"
    config_dir: Path = REPO_ROOT / "config"
    video_dir: Path = REPO_ROOT / "video"

    def ffmpeg(self, tool: str = "ffmpeg") -> Path:
        """Absolute path of ffmpeg/ffprobe; `.exe` is appended on Windows when present."""
        exe = self.ffmpeg_dir / f"{tool}.exe"
        return exe if exe.exists() else self.ffmpeg_dir / tool


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
