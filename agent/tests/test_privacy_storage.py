from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from agent.llm.router import LLMRouter
from agent.privacy.pii import regex_scrub, scrub
from agent.rag.loaders import UnsupportedFileError
from agent.schemas.video_spec import VideoSpec
from agent.settings import REPO_ROOT
from agent.storage import ProjectStore
from agent.tests.conftest import SOURCES


def test_regex_scrub_finds_personal_data() -> None:
    text = (
        "Patient: Jane Example\nDate of birth: 12/03/1971\nMRN: KX-448812\nPhone: +995 555 12 34 56\n"
        "Email: jane@example.com\nპირადი ნომერი: 01024012345\nTake 500 mg every 6 hours. Step 3."
    )
    clean, found = regex_scrub(text)
    kinds = {r.kind for r in found}
    assert {"name", "dob", "mrn", "phone", "email", "id"} <= kinds
    assert "Jane" not in clean and "448812" not in clean and "jane@" not in clean
    assert "500 mg every 6 hours" in clean and "Step 3" in clean
    assert all("*" in r.preview or len(r.preview) <= 1 for r in found)


def test_flash_pass_redacts_missed_names(router: LLMRouter) -> None:
    router.backend.responses["pii_scrub"] = {"spans": [{"text": "Nino Beridze", "kind": "name"}]}  # type: ignore[attr-defined]
    clean, found, usage = scrub("Call Nino Beridze if it hurts.", router)
    assert "Nino" not in clean and found[-1].kind == "name"
    assert usage.by_role("pii_scrub") is not None


def test_project_store_lifecycle(tmp_path: Path, router: LLMRouter) -> None:
    ps = ProjectStore(tmp_path)
    pid = ps.create("demo")
    assert ps.exists(pid) and not ps.exists("../etc") and ps.meta(pid)["title"] == "demo"
    assert [p["id"] for p in ps.list_projects()] == [pid]
    with pytest.raises(ValueError):
        ps.dir("BAD ID")
    doc, _ = ps.add_source(pid, "discharge.md", (SOURCES / "discharge-knee-en.md").read_bytes(), router)
    assert doc.lang == "en" and doc.redactions
    assert "Jane Example" not in doc.text and "500 mg" in doc.text
    assert ps.sources(pid)[0].doc_id == doc.doc_id
    with pytest.raises(UnsupportedFileError):
        ps.add_source(pid, "x.exe", b"x")

    spec = VideoSpec.model_validate_json(
        (REPO_ROOT / "data/fixtures/specs/handwash-en.json").read_text("utf-8")
    )
    ps.save_spec(pid, spec)
    assert ps.load_spec(pid, 1) == spec
    (ps.version_dir(pid, 1) / "preview").mkdir()
    (ps.version_dir(pid, 1) / "preview" / "video.mp4").write_bytes(b"x")
    v = ps.versions(pid)
    assert (
        v[0]["version"] == 1
        and v[0]["preview"]["mp4"]
        and not v[0]["preview"]["srt"]
        and v[0]["final"] is None
    )

    ps.record_approval(pid, 1, "nino")
    assert ps.audit(pid)[0]["user"] == "nino"

    raw = next((ps.dir(pid) / "raw").iterdir())
    old = time.time() - 40 * 86400
    os.utime(raw, (old, old))
    assert ps.purge_raw(pid, 30) == 1
    ps.delete(pid)
    assert not ps.exists(pid)
