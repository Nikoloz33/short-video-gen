from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent.api.app import create_app
from agent.cli import main as cli_main
from agent.graph.runner import Runner
from agent.settings import Settings
from agent.tests.conftest import SOURCES, make_runner

H = {"Authorization": "Bearer t"}


@pytest.fixture
def client(settings: Settings) -> Iterator[tuple[TestClient, Runner]]:
    r = make_runner(settings)
    with TestClient(create_app(settings, r)) as c:
        yield c, r
    r.close()


def sse(c: TestClient, url: str, body: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    with c.stream("POST", url, json=body, headers=H) as resp:
        assert resp.status_code == 200
        event = None
        for line in resp.iter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = json.loads(line.split(":", 1)[1])
                assert data["type"] == event
                out.append(data)
    return out


def test_auth_and_health(client: tuple[TestClient, Runner]) -> None:
    c, _ = client
    assert c.get("/api/health").json()["ok"]
    assert c.get("/api/projects").status_code == 401
    assert c.get("/api/projects", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.get("/api/projects?token=t").status_code == 200
    assert c.get("/api/projects/abcdef123456", headers=H).status_code == 404


def test_full_flow_over_http(client: tuple[TestClient, Runner]) -> None:
    c, _ = client
    pid = c.post("/api/projects", json={"title": "Kitchen"}, headers=H).json()["id"]
    assert [p["id"] for p in c.get("/api/projects", headers=H).json()] == [pid]

    with (SOURCES / "discharge-knee-en.md").open("rb") as f:
        up = c.post(f"/api/projects/{pid}/sources", files={"file": ("d.md", f)}, headers=H).json()
    assert {r["kind"] for r in up["redactions"]} >= {"name", "dob", "mrn", "phone"}
    bad = c.post(f"/api/projects/{pid}/sources", files={"file": ("x.exe", b"MZ")}, headers=H)
    assert bad.status_code == 415

    assert c.post(f"/api/projects/{pid}/resume", json={"action": "approve"}, headers=H).status_code == 409
    assert c.post(f"/api/projects/{pid}/messages", json={"text": " "}, headers=H).status_code == 422

    evs = sse(c, f"/api/projects/{pid}/messages", {"text": "A 45-second Georgian video with one quiz"})
    order = [e["type"] for e in evs]
    # SSE order: tokens stream first, cards follow, the review wait and `done` close the run.
    assert order[-1] == "done" and order[-2] == "awaiting_review"
    assert order.index("token") < order.index("card") < order.index("awaiting_review") < order.index("done")
    snap = c.get(f"/api/projects/{pid}", headers=H).json()
    assert snap["status"] == "awaiting_script_review" and snap["pending"]["kind"] == "script"
    assert snap["spec"]["lang"] == "ka" and snap["sources"][0]["redactions"]
    assert any(
        m["card"] and m["card"]["kind"] == "fact_check" for m in snap["messages"] if m["role"] == "agent"
    )

    # Per-claim decisions carry the claim's address; unknown actions are rejected.
    assert c.post(f"/api/projects/{pid}/resume", json={"action": "drop"}, headers=H).status_code == 422
    evs = sse(c, f"/api/projects/{pid}/resume", {"action": "keep_claim", "scene_id": "s2", "index": 0})
    assert any(e["type"] == "card" and e["card"]["kind"] == "fact_check" for e in evs)
    assert evs[-2]["type"] == "awaiting_review"

    evs = sse(c, f"/api/projects/{pid}/resume", {"action": "approve"})
    order = [e["type"] for e in evs]
    assert "render_progress" in order and order.index("render_progress") < order.index("render_done")
    snap = c.get(f"/api/projects/{pid}", headers=H).json()
    v = snap["versions"][-1]
    assert v["preview"]["mp4"]
    assert (
        c.get(f"/api/projects/{pid}/versions/{v['version']}/preview/mp4?token=t").headers["content-type"]
        == "video/mp4"
    )
    assert c.get(f"/api/projects/{pid}/versions/{v['version']}/preview/vtt", headers=H).text.startswith(
        "WEBVTT"
    )
    assert c.get(f"/api/projects/{pid}/versions/{v['version']}/final/mp4", headers=H).status_code == 404
    assert c.get(f"/api/projects/{pid}/versions/{v['version']}/preview/exe", headers=H).status_code == 404


def test_concurrent_runs_are_rejected(client: tuple[TestClient, Runner]) -> None:
    c, r = client
    pid = c.post("/api/projects", json={}, headers=H).json()["id"]
    lock = r.lock(pid)
    lock.acquire()
    try:
        assert c.post(f"/api/projects/{pid}/messages", json={"text": "hi"}, headers=H).status_code == 409
    finally:
        lock.release()


def test_cli_fake_create_and_spend(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("agent.cli.get_settings", lambda: settings)
    rc = cli_main(["--fake", "create", "--source", str(SOURCES / "handwashing-sop-en.md"), "--message",
                   "A 45-second English video", "--approve", "script,video"])  # fmt: skip
    out = capsys.readouterr().out
    assert rc == 0 and "auto-approving script" in out and '"status": "done"' in out
    pid = out.split("project ", 1)[1].split(":", 1)[0]
    assert cli_main(["--fake", "status", pid]) == 0
    assert '"done"' in capsys.readouterr().out
    assert cli_main(["spend"]) == 0


def test_retry_endpoint_rejects_when_nothing_failed(client: tuple[TestClient, Runner]) -> None:
    c, _ = client
    pid = c.post("/api/projects", json={}, headers=H).json()["id"]
    assert c.post(f"/api/projects/{pid}/retry", headers=H).status_code == 409
    assert c.get(f"/api/projects/{pid}", headers=H).json()["can_retry"] is False
