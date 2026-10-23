from __future__ import annotations

import pytest

from agent.schemas.llm_io import DraftRow, DraftScene, ScriptDraft
from agent.schemas.video_spec import SourceRef, VideoSpec
from agent.script import (
    DraftError,
    apply_audio,
    draft_scenes,
    draft_to_spec,
    estimate_speech_s,
    narration_budget_chars,
    next_scene_id,
    outline,
    renumber,
    scene_duration,
    scene_texts,
    with_scene_texts,
)
from agent.settings import REPO_ROOT

SPEC = VideoSpec.model_validate_json((REPO_ROOT / "data/fixtures/specs/handwash-en.json").read_text("utf-8"))


def d(**kw: object) -> DraftScene:
    return DraftScene.model_validate({"narration": "Say it.", "evidence": ["c:1:0"], **kw})


def test_draft_to_spec_numbers_steps_and_copies_quiz() -> None:
    draft = ScriptDraft(
        title="T",
        scenes=[
            d(template="title_card", title="Title"),
            d(template="step_card", text="One", icon="soap"),
            d(template="step_card", text="Two", icon="droplets"),
            d(template="quiz_question", question="Q?", options=["a", "b"], correct_index=1),
            d(template="quiz_answer", explanation="Because."),
            d(
                template="schedule",
                heading="When",
                rows=[DraftRow(time="08:00", text="x", icon="nonexistent")],
            ),
        ],
    )
    spec = draft_to_spec(draft, lang="en", source_lang="en", audience="workplace", target_sec=45,
                         sources=[SourceRef(doc_id="c", title="c")])  # fmt: skip
    steps = [s for s in spec.scenes if s.template == "step_card"]
    assert [(s.step_no, s.total_steps) for s in steps] == [(1, 2), (2, 2)]
    q, a = spec.scenes[3], spec.scenes[4]
    assert q.template == "quiz_question" and q.countdown_s == 5
    assert a.template == "quiz_answer" and a.options == ["a", "b"] and a.correct_index == 1
    assert spec.scenes[5].rows[0].icon is None  # type: ignore[union-attr]
    assert [s.id for s in spec.scenes] == [f"s{i}" for i in range(1, 7)]


def test_missing_icons_and_texts_are_repaired() -> None:
    scenes = draft_scenes(
        [
            d(template="step_card", narration="Put on clean gloves before touching food."),
            d(template="warning", heading="Hot", narration="Hot water can scald your hands."),
            d(template="do_dont", do_text="Use soap", dont_text="Never skip gloves"),
        ],
        "en",
    )
    assert scenes[0].icon == "gloves" and scenes[0].text  # type: ignore[union-attr]
    assert scenes[1].text and scenes[1].icon  # type: ignore[union-attr]
    assert scenes[2].do_icon == "soap" and scenes[2].dont_icon == "gloves"  # type: ignore[union-attr]


def test_invalid_draft_reports_problems() -> None:
    with pytest.raises(DraftError) as e:
        draft_scenes([d(template="checklist", heading="H", items=["only one"])], "en")
    assert "checklist" in e.value.problems[0]
    with pytest.raises(DraftError):
        draft_to_spec(ScriptDraft(title="T", scenes=[]), lang="en", source_lang="en", audience="workplace",
                      target_sec=45, sources=[])  # fmt: skip


def test_scene_texts_round_trip() -> None:
    for s in SPEC.scenes:
        texts = scene_texts(s)
        again = with_scene_texts(s, "N", [t.upper() for t in texts])
        assert again.narration == "N"
        assert scene_texts(again) == [t.upper() for t in texts]


def test_durations_audio_and_helpers() -> None:
    step = SPEC.scenes[2]
    assert scene_duration(step, 1.0) >= 3.5
    assert scene_duration(step, 6.0) == pytest.approx(0.3 + 6.0 + 0.7)
    quiz = SPEC.scene("s8")
    assert scene_duration(quiz, 2.0) >= 4 + 2  # reading time + countdown
    with_audio = apply_audio(step, "cache/tts/x.wav", 3.2)
    assert with_audio.audio is not None and with_audio.audio.start_s == 0.3
    assert with_audio.duration_s >= 0.3 + 3.2
    assert estimate_speech_s("x" * 75, "ka") == pytest.approx(10.0)
    assert narration_budget_chars(60, "ka") == 360
    assert next_scene_id(SPEC) == "s11"
    shuffled = SPEC.model_copy(update={"scenes": list(reversed(SPEC.scenes))})
    nums = [s.step_no for s in renumber(shuffled).scenes if s.template == "step_card"]
    assert nums == [1, 2, 3]
    assert "[s8] quiz_question" in outline(SPEC)


def test_misnamed_fields_are_coerced_into_valid_scenes() -> None:
    # Seen live: a warning with "title" instead of "heading", a summary with "items" instead of
    # "points", stray fields of other templates, and over-long lists and narration.
    scenes = draft_scenes(
        [
            d(template="warning", title="Never reuse gloves", text="Throw them away.", items=["x"]),
            d(template="summary", heading="Remember", items=["One", "Two", "Three", "Four", "Five"]),
            d(template="checklist", heading="Kit", items=["a", "b", "c", "d", "e", "f", "g"],
              narration="Long. " * 200),
        ],
        "en",
    )  # fmt: skip
    warn, summary, checklist = (s.model_dump() for s in scenes)
    assert warn["heading"] == "Never reuse gloves" and "items" not in warn
    assert summary["points"] == ["One", "Two", "Three", "Four"]
    assert len(checklist["items"]) == 5 and len(checklist["narration"]) <= 400
    assert checklist["narration"].endswith(".")


def test_required_heading_falls_back_to_the_first_narration_sentence() -> None:
    (scene,) = draft_scenes(
        [d(template="checklist", items=["a", "b"], narration="Check your kit. Then start.")], "en"
    )
    assert scene.model_dump()["heading"] == "Check your kit."
