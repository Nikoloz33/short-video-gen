"""One call per distinct model in config/models.yaml to check availability in the configured location.

    uv run python scripts/probe_models.py [--location eu]

Costs a fraction of a cent. Uses Application Default Credentials (gcloud auth application-default login).
"""

from __future__ import annotations

import argparse
import sys
import time

from google import genai
from google.genai import types

from agent.config import load_models
from agent.logging import configure, get_logger
from agent.settings import get_settings

log = get_logger("probe")


def main() -> int:
    configure()
    settings = get_settings()
    models = load_models()
    parser = argparse.ArgumentParser()
    parser.add_argument("--location", default=settings.google_cloud_location or models.location)
    args = parser.parse_args()
    client = genai.Client(vertexai=True, project=settings.google_cloud_project, location=args.location)

    seen: dict[str, str] = {}
    for role, cfg in models.roles.items():
        seen.setdefault(cfg.model, role)
    failures = 0
    for model, role in seen.items():
        cfg = models.role(role)
        t0 = time.perf_counter()
        try:
            if role == "embeddings":
                r = client.models.embed_content(
                    model=model,
                    contents="hand washing",
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_QUERY", output_dimensionality=cfg.dimensions
                    ),
                )
                detail = f"dims={len(r.embeddings[0].values or []) if r.embeddings else 0}"
            elif role == "tts":
                r = client.models.generate_content(
                    model=model,
                    contents="Wash your hands.",
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            language_code="en-US",
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=cfg.voice or "Kore"
                                )
                            ),
                        ),
                    ),
                )
                part = r.candidates[0].content.parts[0] if r.candidates and r.candidates[0].content else None
                blob = part.inline_data if part and part.inline_data else None
                detail = (
                    f"audio {blob.mime_type if blob else '?'} {len(blob.data or b'') if blob else 0} bytes"
                )
            else:
                thinking = (
                    types.ThinkingConfig(thinking_level=cfg.thinking_level)  # type: ignore[arg-type]
                    if cfg.thinking_level
                    else None
                )
                r = client.models.generate_content(
                    model=model,
                    contents="Reply with the single word OK.",
                    config=types.GenerateContentConfig(temperature=cfg.temperature, thinking_config=thinking),
                )
                usage = r.usage_metadata
                detail = f"text={r.text!r} in={usage.prompt_token_count if usage else '?'}"
            log.info("ok", model=model, role=role, ms=round((time.perf_counter() - t0) * 1000), detail=detail)
        except Exception as e:  # a probe reports every failure
            failures += 1
            log.error("failed", model=model, role=role, error=str(e)[:400])
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
