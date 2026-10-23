from __future__ import annotations

from typing import Any

from agent.graph.runner import Runner
from agent.graph.state import RESET, reports_reducer, usage_reducer
from agent.llm.fake_scenario import scenario_responses
from agent.settings import Settings
from agent.tests.conftest import events, make_runner, new_project, nodes, types


def _to_script_review(
    r: Runner, pid: str, msg: str = "A 45-second Georgian training video with one quiz"
) -> list[dict[str, Any]]:
    evs = events(r.run(pid, message=msg))
    assert evs[-1]["type"] == "done"
    return evs


def test_full_flow_with_both_reviews(runner: Runner) -> None:
    pid = new_project(runner)
    evs = _to_script_review(runner, pid)
    ns = nodes(evs)
    assert ns[:5] == ["intake", "ingest_source", "plan", "write_script", "fact_check"]
    assert ("translate" in ns and ns[-2:] == ["present_script", "review_script"]) or "present_script" in ns
    review = [e for e in evs if e["type"] == "awaiting_review"]
    assert review and review[0]["kind"] == "script"
    assert runner.pending_interrupt(pid) == {"kind": "script", "version": 2}
    # Tokens stream before cards; the plan + fact-check + script cards are posted.
    cards = [e["card"]["kind"] for e in evs if e["type"] == "card"]
    assert {"source", "plan", "fact_check", "translation", "script"} <= set(cards)
    assert types(evs).index("token") < types(evs).index("card")

    evs = events(runner.run(pid, resume={"action": "approve", "user": "u1"}))
    assert [
        n
        for n in nodes(evs)
        if n in {"narrate", "layout_check", "render_preview", "validate_video", "present_video"}
    ] == ["narrate", "layout_check", "render_preview", "validate_video", "present_video"]
    progress = [e for e in evs if e["type"] == "render_progress"]
    assert progress[0]["stage"] == "tts" and any(e.get("preset") == "preview" for e in progress)
    assert runner.pending_interrupt(pid) == {"kind": "video", "version": 2}

    evs = events(runner.run(pid, resume={"action": "approve", "user": "u1"}))
    assert "render_final" in nodes(evs) and nodes(evs)[-1] == "done"
    st = runner.state(pid)
    assert st["status"] == "done" and st["render"]["final"]["checks"]
    assert runner.deps.projects.audit(pid)[0]["user"] == "u1"
    assert runner.state(pid)["usage"]["roles"]


def test_resume_after_restart(settings: Settings) -> None:
    r1 = make_runner(settings)
    pid = new_project(r1)
    _to_script_review(r1, pid)
    r1.close()
    r2 = make_runner(settings)  # a "restarted server": new graph over the same SQLite file
    assert r2.pending_interrupt(pid) == {"kind": "script", "version": 2}
    evs = events(r2.run(pid, resume={"action": "approve"}))
    assert "render_preview" in nodes(evs)
    r2.close()


def test_chat_edit_recomputes_only_what_changed(runner: Runner) -> None:
    pid = new_project(runner)
    _to_script_review(runner, pid)
    events(runner.run(pid, resume={"action": "approve"}))
    before = runner.state(pid)["tts_stats"]
    assert before["synthesized"] == 9
    # Free text while the video review waits = an edit.
    evs = events(runner.run(pid, message="make step 3 shorter and use the gloves icon"))
    ns = nodes(evs)
    assert ns[:2] == ["review_video", "chat_edit"] and "apply_edit" in ns
    assert "write_script" not in ns and "translate" not in ns and "plan" not in ns
    checked = [e["scene_id"] for e in evs if e["type"] == "fact_progress"]
    assert len(checked) == 1  # only the edited scene is fact-checked
    after = runner.state(pid)["tts_stats"]
    assert after["synthesized"] == 1 and after["cache_hits"] == 8
    edit_card = next(e["card"] for e in evs if e["type"] == "card" and e["card"]["kind"] == "edit")
    assert edit_card["version"] == 3
    assert runner.pending_interrupt(pid) == {"kind": "video", "version": 3}


def test_icon_only_edit_skips_fact_check_and_tts(runner: Runner) -> None:
    pid = new_project(runner)
    _to_script_review(runner, pid)
    events(runner.run(pid, resume={"action": "approve"}))
    responses: Any = runner.deps.router.backend
    responses.responses["chat_edit"] = {
        "ops": [{"op": "set_icon", "scene_id": "s2", "icon": "gloves"}],
        "reply": "ok",
    }
    evs = events(runner.run(pid, message="use the gloves icon on scene 2"))
    assert "fact_reduce" not in nodes(evs)
    assert runner.state(pid)["tts_stats"]["synthesized"] == 0


def test_language_switch_retranslates(runner: Runner) -> None:
    pid = new_project(runner)
    _to_script_review(runner, pid, "A 45-second English video")
    fake: Any = runner.deps.router.backend
    fake.responses["chat_edit"] = {"ops": [{"op": "set_language", "language": "ka"}], "reply": "ok"}
    evs = events(runner.run(pid, message="switch to Georgian"))
    assert "translate" in nodes(evs)
    assert runner.state(pid)["spec"]["lang"] == "ka"


def test_bad_edits_are_explained_not_applied(runner: Runner) -> None:
    pid = new_project(runner)
    _to_script_review(runner, pid)
    fake: Any = runner.deps.router.backend
    version = runner.state(pid)["spec"]["version"]
    for ops in (
        [{"op": "set_icon", "scene_id": "s2", "icon": "unicorn"}],
        [{"op": "delete_scene", "scene_id": "s99"}],
        [{"op": "reorder", "order": ["s1"]}],
        [{"op": "set_voice", "voice": "Robot"}],
        [],
    ):
        fake.responses["chat_edit"] = {"ops": ops, "reply": "Sorry, I can't."}
        evs = events(runner.run(pid, message="do something"))
        text = "".join(e.get("text", "") for e in evs if e["type"] == "token")
        assert "couldn't apply" in text or "Sorry" in text
        assert runner.state(pid)["spec"]["version"] == version
        assert runner.pending_interrupt(pid) == {"kind": "script", "version": version}


def test_set_text_reorder_delete_voice(runner: Runner) -> None:
    pid = new_project(runner)
    _to_script_review(runner, pid)
    fake: Any = runner.deps.router.backend
    ids = [s["id"] for s in runner.state(pid)["spec"]["scenes"]]
    fake.responses["chat_edit"] = {
        "ops": [
            {
                "op": "set_text",
                "scene_id": "step 1",
                "field": "narration",
                "value": "Wet your hands with warm running water.",
            },
            {
                "op": "set_text",
                "scene_id": ids[-1],
                "field": "points",
                "index": 0,
                "value": "Wet and apply soap",
            },
            {"op": "reorder", "order": [ids[0], ids[2], ids[1], *ids[3:]]},
            {"op": "delete_scene", "scene_id": ids[-2]},
            {"op": "set_voice", "voice": "Puck"},
        ],
        "reply": "Done.",
    }
    events(runner.run(pid, message="edit"))
    spec = runner.state(pid)["spec"]
    assert spec["voice"] == "Puck" and len(spec["scenes"]) == len(ids) - 1
    assert [s["id"] for s in spec["scenes"]][:3] == [ids[0], ids[2], ids[1]]


def test_add_quiz_and_target_duration(runner: Runner) -> None:
    pid = new_project(runner)
    _to_script_review(runner, pid)
    fake: Any = runner.deps.router.backend
    n = len(runner.state(pid)["spec"]["scenes"])
    fake.responses["chat_edit"] = {
        "ops": [{"op": "add_quiz", "after": "s2", "instruction": "about gloves"}],
        "reply": "ok",
    }
    events(runner.run(pid, message="add a quiz about gloves"))
    assert len(runner.state(pid)["spec"]["scenes"]) == n + 1  # the fake rewrite returns one scene
    fake.responses["chat_edit"] = {"ops": [{"op": "set_target_duration", "target_sec": 30}], "reply": "ok"}
    evs = events(runner.run(pid, message="make it 30 seconds"))
    assert "write_script" in nodes(evs) and runner.state(pid)["request"]["target_sec"] == 30


def test_fix_loop_is_capped_and_blocks_export(settings: Settings) -> None:
    responses = scenario_responses()
    responses["fact_check_verdict"] = lambda req: {
        "verdicts": [{"claim_index": 0, "verdict": "unsupported", "why": "not in source"}]
    }
    r = make_runner(settings, responses)
    pid = new_project(r)
    evs = _to_script_review(r, pid, "A 45-second English video")
    ns = nodes(evs)
    # Same failures after a fix -> the loop exits early instead of burning both attempts.
    assert 1 <= ns.count("fix_script") <= 2
    assert "present_script" in ns
    events(r.run(pid, resume={"action": "approve"}))
    evs = events(r.run(pid, resume={"action": "approve"}))
    assert r.state(pid)["status"] == "blocked" and "render_final" not in nodes(evs)
    r.close()


def test_spend_cap_stops_the_run(settings: Settings) -> None:
    r = make_runner(settings.model_copy(update={"max_run_cost_usd": 0.0000001}))
    pid = new_project(r)
    evs = events(r.run(pid, message="A video"))
    assert any(e["type"] == "error" and e["code"] == "budget" for e in evs)
    r.close()


def test_out_of_scope_and_missing_source(settings: Settings) -> None:
    responses = scenario_responses()
    responses["intake"] = {
        "in_scope": False,
        "refusal_reason": "I only make instructional videos.",
        "reply": "-",
    }
    r = make_runner(settings, responses)
    pid = new_project(r)
    evs = events(r.run(pid, message="Write me a song"))
    assert r.state(pid)["status"] == "refused" and nodes(evs) == ["intake"]
    r.close()
    r2 = make_runner(settings)
    pid2 = r2.deps.projects.create("empty")
    events(r2.run(pid2, message="A video please"))
    assert r2.state(pid2)["status"] == "need_source"
    r2.close()


def test_regenerate_from_script_review(runner: Runner) -> None:
    pid = new_project(runner)
    _to_script_review(runner, pid)
    evs = events(runner.run(pid, resume={"action": "regenerate"}))
    assert "write_script" in nodes(evs) and runner.pending_interrupt(pid)["kind"] == "script"  # type: ignore[index]


def test_reducers() -> None:
    assert reports_reducer([{"a": 1}], [{"b": 2}]) == [{"a": 1}, {"b": 2}]
    assert reports_reducer([{"a": 1}], [RESET]) == []
    u = usage_reducer({"roles": [{"role": "plan", "model": "m", "calls": 1, "cost_usd": 0.1}]},
                      {"roles": [{"role": "plan", "model": "m", "calls": 2, "cost_usd": 0.2}]})  # fmt: skip
    assert u["roles"][0]["calls"] == 3


def test_retry_continues_from_the_checkpoint(settings: Settings) -> None:
    from agent.llm.types import RetryableError

    responses = scenario_responses()
    script = responses["write_script"]
    calls = {"n": 0}

    def flaky(req: Any) -> Any:
        calls["n"] += 1
        if calls["n"] <= 6:  # every retry attempt of the first run fails
            raise RetryableError("quota", 503)
        return script(req)

    responses["write_script"] = flaky
    r = make_runner(settings, responses)
    r.deps.router._sleep = lambda _s: None
    pid = new_project(r)
    evs = events(r.run(pid, message="A 45-second English video"))
    assert any(e["type"] == "error" for e in evs) and evs[-1]["can_retry"] is True
    assert r.can_retry(pid)
    evs = events(r.run(pid, retry=True))
    ns = nodes(evs)
    assert ns[0] == "write_script" and "intake" not in ns and "plan" not in ns
    assert r.pending_interrupt(pid) == {"kind": "script", "version": 1}
    assert not r.can_retry(pid)
    r.close()
