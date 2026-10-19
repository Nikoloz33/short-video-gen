"""Opt-in smoke tests against real Vertex AI (cost: well under one cent).

uv run pytest -m live agent/tests/test_live_router.py --no-cov
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from agent.llm.factory import build_router

pytestmark = pytest.mark.live


class Pair(BaseModel):
    english: str
    georgian: str


def test_live_text_structured_tts_embed() -> None:
    router = build_router()
    assert "OK" in router.text("intake", "Reply with the single word OK.").text.upper()
    r = router.structured("intake", "Translate 'water' into Georgian.", Pair)
    assert r.value.english.lower() == "water"
    assert any("ა" <= ch <= "ჿ" for ch in r.value.georgian)
    audio = router.tts("Wash your hands.", "en-US")
    assert len(audio.data) > 1000
    vec, _ = router.embed("hand washing", "RETRIEVAL_QUERY")
    assert len(vec) == 768
