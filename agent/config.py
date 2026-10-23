"""Typed access to config/models.yaml (the only place model names appear) and config/app.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from agent.settings import get_settings

Language = Literal["ka", "en"]


class Pricing(BaseModel):
    """USD per 1M tokens. `audio_out_per_m` applies to TTS audio output tokens."""

    in_per_m: float = 0.0
    out_per_m: float = 0.0
    audio_out_per_m: float = 0.0


class ModelRole(BaseModel):
    model: str
    temperature: float | None = None
    thinking_level: Literal["LOW", "MEDIUM", "HIGH"] | None = None
    voice: str | None = None
    dimensions: int | None = None
    pricing: Pricing = Field(default_factory=Pricing)
    #: Role to use when this model stays rate-limited (429) after all retries.
    fallback: str | None = None


class ModelsConfig(BaseModel):
    location: str = "eu"
    roles: dict[str, ModelRole]

    def role(self, name: str) -> ModelRole:
        try:
            return self.roles[name]
        except KeyError as e:
            raise KeyError(f"unknown model role {name!r}; add it to config/models.yaml") from e


class LanguageConfig(BaseModel):
    tts_code: str
    chars_per_sec: float = Field(gt=0)


class RenderPreset(BaseModel):
    width: int
    height: int
    fps: int
    scale: float = 1.0
    crf: int = 18


class AppConfig(BaseModel):
    languages: dict[Language, LanguageConfig]
    min_duration_s: float = 30
    max_duration_s: float = 300
    hard_cap_s: float = 300
    fix_loop_cap: int = 2
    recursion_limit: int = 80
    upload_retention_days: int = 30
    presets: dict[Literal["preview", "final"], RenderPreset]


def _load_yaml(path: Path) -> object:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=4)
def load_models(config_dir: Path | None = None) -> ModelsConfig:
    root = config_dir or get_settings().config_dir
    return ModelsConfig.model_validate(_load_yaml(root / "models.yaml"))


@lru_cache(maxsize=4)
def load_app(config_dir: Path | None = None) -> AppConfig:
    root = config_dir or get_settings().config_dir
    return AppConfig.model_validate(_load_yaml(root / "app.yaml"))
