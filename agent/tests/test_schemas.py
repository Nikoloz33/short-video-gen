from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agent import catalog
from agent.schemas import export
from agent.schemas.gemini import gemini_schema
from agent.schemas.video_spec import TEMPLATES, VideoSpec
from agent.settings import REPO_ROOT

FIXTURES = REPO_ROOT / "data" / "fixtures" / "specs"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _patch(doc: Any, case: dict[str, Any]) -> Any:
    doc = copy.deepcopy(doc)
    *parents, last = case["path"]
    node = doc
    for p in parents:
        node = node[p]
    if case.get("delete"):
        del node[last]
    else:
        node[last] = case["value"]
    return doc


def test_valid_fixture_parses() -> None:
    spec = VideoSpec.model_validate(_load("handwash-en.json"))
    assert spec.lang == "en"
    assert len(spec.scenes) == 10
    assert 30 <= spec.total_s <= 60
    assert spec.scene("s8").template == "quiz_question"
    with pytest.raises(KeyError):
        spec.scene("nope")


def test_round_trip_is_stable() -> None:
    spec = VideoSpec.model_validate(_load("handwash-en.json"))
    again = VideoSpec.model_validate_json(spec.model_dump_json())
    assert again == spec


_INVALID = _load("invalid.json")


@pytest.mark.parametrize(
    "case",
    _INVALID["cases"] + _INVALID["_python_only"],
    ids=lambda c: c["name"],
)
def test_invalid_fixtures_rejected(case: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        VideoSpec.model_validate(_patch(_load("handwash-en.json"), case))


def test_templates_enum_matches_union() -> None:
    schema = VideoSpec.model_json_schema()
    union = schema["properties"]["scenes"]["items"]["oneOf"]
    assert len(union) == len(TEMPLATES) == 11


def test_export_is_current() -> None:
    """The committed JSON Schema must match the models (else run the export + codegen)."""
    assert export.main(["--check"]) == 0


def test_export_writes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "spec.schema.json"
    monkeypatch.setattr(export, "schema_path", lambda: target)
    assert export.main(["--check"]) == 1
    assert export.main([]) == 0
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["title"] == "VideoSpec"
    assert "title" not in data["$defs"]["AudioClip"]["properties"]["src"]
    assert export.main(["--check"]) == 0


def test_gemini_schema_is_flat() -> None:
    flat = gemini_schema(VideoSpec)
    text = json.dumps(flat)
    assert "$ref" not in text
    assert "$defs" not in text
    assert "additionalProperties" not in text
    scene = flat["properties"]["scenes"]["items"]["anyOf"][0]
    assert scene["properties"]["template"]["enum"] == ["title_card"]
    audio = scene["properties"]["audio"]
    assert audio["nullable"] is True
    assert audio["type"] == "object"


def test_catalog_lookup_and_prompt_list() -> None:
    assert "gloves" in catalog.icon_names()
    assert len(catalog.icons()) >= 120
    assert catalog.search_icons("ხელთათმანი")[0] == "gloves"
    assert catalog.search_icons("gloves")[0] == "gloves"
    assert catalog.search_icons("  ") == []
    lines = catalog.icon_prompt_list().splitlines()
    assert any(line.startswith("gloves: ") for line in lines)
