"""Flagged claims are decided by the reviewer right away, instead of by repeated repair loops."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from agent.graph.nodes.edit import edit_context
from agent.graph.nodes.script import draft_gate, layout_hint, text_issues
from agent.graph.runner import Runner
from agent.llm.fake_scenario import scenario_responses
from agent.schemas.video_spec import VideoSpec
from agent.settings import REPO_ROOT, Settings
from agent.tests.conftest import events, make_runner, new_project, nodes

SPEC = VideoSpec.model_validate_json((REPO_ROOT / "data/fixtures/specs/handwash-en.json").read_text("utf-8"))


def _flagged_runner(settings: Settings) -> Runner:
    responses = scenario_responses()
    responses["fact_check_verdict"] = lambda req: {
        "verdicts": [{"claim_index": 0, "verdict": "unsupported", "why": "not in source"}]
    }
    return make_runner(settings, responses)


def _to_review(r: Runner) -> str:
    pid = new_project(r)
    evs = events(r.run(pid, message="A 45-second English video"))
    assert evs[-1]["type"] == "done"
    # One automatic repair at most: the user decides the rest.
    assert nodes(evs).count("fix_script") <= 1
    assert r.pending_interrupt(pid) is not None
    return pid


def _ledger(evs: list[dict[str, Any]]) -> dict[str, Any]:
    return [e["card"] for e in evs if e["type"] == "card" and e["card"]["kind"] == "fact_check"][-1]


def test_keep_one_claim_then_keep_the_rest_and_export(settings: Settings) -> None:
    r = _flagged_runner(settings)
    pid = _to_review(r)
    flagged = [
        (s, c)
        for s in r.state(pid)["fact_report"]["scenes"]
        for c in s["claims"]
        if c["verdict"] != "supported"
    ]
    assert flagged
    scene, claim = flagged[0]
    sid, idx = scene["scene_id"], scene["claims"].index(claim)

    evs = events(r.run(pid, resume={"action": "keep_claim", "scene_id": sid, "index": idx, "user": "nurse"}))
    card = _ledger(evs)
    assert card["flagged"] == len(flagged) - 1
    kept = next(c for s in card["scenes"] if s["scene_id"] == sid for c in s["claims"] if c["index"] == idx)
    assert kept["confirmed_by"] == "nurse"
    assert "fix_script" not in nodes(evs) and r.pending_interrupt(pid) is not None

    evs = events(r.run(pid, resume={"action": "keep_flagged", "user": "nurse"}))
    assert "narrate" in nodes(evs) and (r.pending_interrupt(pid) or {}).get("kind") == "video"
    evs = events(r.run(pid, resume={"action": "approve", "user": "nurse"}))
    assert "render_final" in nodes(evs) and r.state(pid)["status"] == "done"
    audit = r.deps.projects.audit(pid)
    assert [a["event"] for a in audit].count("claim_keep") == len(flagged)
    assert all(a["user"] == "nurse" for a in audit)
    r.close()


def test_remove_flagged_rewrites_only_those_scenes(settings: Settings) -> None:
    r = _flagged_runner(settings)
    pid = _to_review(r)
    sids = {s["scene_id"] for s in r.state(pid)["fact_report"]["scenes"] if not s["ok"]}
    evs = events(r.run(pid, resume={"action": "remove_flagged", "user": "u"}))
    assert "fix_script" in nodes(evs)
    st = r.state(pid)
    assert not st.get("fix_requests")
    fix = [e["card"] for e in evs if e["type"] == "card" and e["card"]["kind"] == "fix"][-1]
    assert set(fix["scenes"]) <= sids
    assert {a["event"] for a in r.deps.projects.audit(pid)} == {"claim_remove"}
    # Back at the review, never in an automatic loop.
    assert r.pending_interrupt(pid) is not None and nodes(evs).count("fix_script") == 1
    r.close()


def test_fix_flagged_hands_the_claims_to_the_agent(settings: Settings) -> None:
    r = _flagged_runner(settings)
    pid = _to_review(r)
    evs = events(r.run(pid, resume={"action": "fix_flagged", "user": "u"}))
    assert "fix_script" in nodes(evs) and r.pending_interrupt(pid) is not None
    r.close()


def test_edit_context_names_layout_problems_and_flagged_claims() -> None:
    state: Any = {
        "messages": [HumanMessage("make it Georgian"), AIMessage("Done."), HumanMessage("remove that text")],
        "layout_issues": [{"scene_id": "s4", "field": "text", "message": "too long (4/3 lines)"}],
        "fact_report": {"scenes": [{"scene_id": "s2", "ok": False, "claims": [
            {"text": "Use hot water", "kind": "fact", "verdict": "unsupported",
             "llm_verdict": "unsupported", "why": "not in source"}]}]},
    }  # fmt: skip
    ctx = edit_context(state)
    assert "make it Georgian" in ctx and "remove that text" not in ctx
    assert "[s4] text: too long" in ctx and "[s2] Use hot water (unsupported)" in ctx
    assert edit_context({"messages": []}) == "(no earlier messages)"  # type: ignore[typeddict-item]


def test_draft_gate_asks_for_cuts_with_a_character_target(runner: Runner) -> None:
    assert draft_gate(runner.deps, SPEC, SPEC.total_s) == []
    problems = draft_gate(runner.deps, SPEC, 30)
    assert problems and "cut about" in problems[0] and "characters" in problems[0]
    runner.deps.renderer.check_issues = [  # type: ignore[attr-defined]
        {
            "scene_id": "s3",
            "field": "text",
            "code": "text_overflow",
            "message": 'too long (3/2 lines): "' + "y" * 60 + '"',
        },
        {"scene_id": "-", "field": "-", "code": "total_duration", "message": "too long"},
    ]
    issues = text_issues(runner.deps, SPEC)
    assert [i["code"] for i in issues] == ["text_overflow"]  # durations wait for narration
    problems = draft_gate(runner.deps, SPEC, SPEC.total_s)
    assert problems == ["[s3] " + layout_hint(issues[0])] and "at most 34 characters" in problems[0]


def test_layout_hint_gives_a_length_target() -> None:
    hint = layout_hint(
        {"field": "text", "code": "text_overflow", "message": 'too long (4/2 lines): "' + "x" * 100 + '"'}
    )
    assert "at most 42 characters" in hint
    assert "a third" in layout_hint({"field": "-", "code": "total_duration", "message": "too long"})
