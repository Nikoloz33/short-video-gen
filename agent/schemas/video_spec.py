"""The video contract. JSON Schema is exported from these models and TS types + zod validators are
generated for `video/` (see agent.schemas.export and video/scripts/codegen.ts). Change the contract
here, then run the export + codegen; CI fails when the generated files are stale."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from agent.catalog import icon_names

Lang = Literal["ka", "en"]
Audience = Literal["workplace", "patient"]
TemplateName = Literal[
    "title_card",
    "step_card",
    "do_dont",
    "checklist",
    "warning",
    "timer",
    "schedule",
    "quiz_question",
    "quiz_answer",
    "summary",
    "disclaimer",
]
TEMPLATES: tuple[TemplateName, ...] = TemplateName.__args__  # type: ignore[attr-defined]


def _known_icon(name: str) -> str:
    if name not in icon_names():
        raise ValueError(f"unknown icon {name!r}: pick a name from the icon catalog")
    return name


IconName = Annotated[str, AfterValidator(_known_icon)]
ShortText = Annotated[str, Field(min_length=1, max_length=140)]
SceneId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$")]


class _Model(BaseModel):
    # Fields with defaults are still required in the exported (serialization) schema, so the
    # generated TS types have no optional-but-always-present fields.
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class AudioClip(_Model):
    src: str = Field(min_length=1, description="URL or path of the narration clip")
    duration_s: float = Field(gt=0, le=30, description="Measured clip length in seconds")
    start_s: float = Field(ge=0, le=5, description="Clip start relative to the scene start")


class SceneBase(_Model):
    id: SceneId
    narration: str = Field(min_length=1, max_length=400)
    evidence: list[str] = Field(default_factory=list, description="Source chunk ids supporting the scene")
    duration_s: float = Field(gt=0, le=30)
    audio: AudioClip | None = None


class TitleCardScene(SceneBase):
    template: Literal["title_card"]
    title: ShortText
    subtitle: ShortText | None = None
    icon: IconName | None = None


class StepCardScene(SceneBase):
    template: Literal["step_card"]
    step_no: int = Field(ge=1, le=20)
    total_steps: int = Field(ge=1, le=20)
    icon: IconName
    text: ShortText

    @model_validator(mode="after")
    def _step_in_range(self) -> StepCardScene:
        if self.step_no > self.total_steps:
            raise ValueError(f"step_no {self.step_no} > total_steps {self.total_steps}")
        return self


class DoDontScene(SceneBase):
    template: Literal["do_dont"]
    do_text: ShortText
    do_icon: IconName
    dont_text: ShortText
    dont_icon: IconName


class ChecklistScene(SceneBase):
    template: Literal["checklist"]
    heading: ShortText
    items: list[ShortText] = Field(min_length=2, max_length=5)


class WarningScene(SceneBase):
    template: Literal["warning"]
    heading: ShortText
    text: ShortText
    icon: IconName


class TimerScene(SceneBase):
    template: Literal["timer"]
    label: ShortText
    seconds: int = Field(ge=1, le=600)
    icon: IconName


class ScheduleRow(_Model):
    time: Annotated[str, Field(min_length=1, max_length=24)]
    text: ShortText
    icon: IconName | None = None


class ScheduleScene(SceneBase):
    template: Literal["schedule"]
    heading: ShortText
    rows: list[ScheduleRow] = Field(min_length=1, max_length=5)


class _QuizBase(SceneBase):
    question: ShortText
    options: list[ShortText] = Field(min_length=2, max_length=4)
    correct_index: int = Field(ge=0, le=3)

    @model_validator(mode="after")
    def _correct_in_range(self) -> _QuizBase:
        if self.correct_index >= len(self.options):
            raise ValueError(f"correct_index {self.correct_index} outside {len(self.options)} options")
        return self


class QuizQuestionScene(_QuizBase):
    template: Literal["quiz_question"]
    countdown_s: int = Field(ge=3, le=10)


class QuizAnswerScene(_QuizBase):
    template: Literal["quiz_answer"]
    explanation: ShortText


class SummaryScene(SceneBase):
    template: Literal["summary"]
    heading: ShortText
    points: list[ShortText] = Field(min_length=2, max_length=4)


class DisclaimerScene(SceneBase):
    template: Literal["disclaimer"]
    heading: ShortText
    text: Annotated[str, Field(min_length=1, max_length=300)]


Scene = Annotated[
    TitleCardScene
    | StepCardScene
    | DoDontScene
    | ChecklistScene
    | WarningScene
    | TimerScene
    | ScheduleScene
    | QuizQuestionScene
    | QuizAnswerScene
    | SummaryScene
    | DisclaimerScene,
    Field(discriminator="template"),
]


class SourceRef(_Model):
    doc_id: str = Field(min_length=1)
    title: str = Field(min_length=1)


class VideoSpec(_Model):
    version: int = Field(default=1, ge=1)
    title: ShortText
    lang: Lang
    source_lang: Lang
    audience: Audience
    voice: str = "Kore"
    theme: str = "default"
    target_sec: float = Field(ge=15, le=90)
    scenes: list[Scene] = Field(min_length=1, max_length=24)
    sources: list[SourceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> VideoSpec:
        ids = [s.id for s in self.scenes]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate scene ids: {', '.join(dupes)}")
        return self

    @property
    def total_s(self) -> float:
        return sum(s.duration_s for s in self.scenes)

    def scene(self, scene_id: str) -> Scene:
        for s in self.scenes:
            if s.id == scene_id:
                return s
        raise KeyError(scene_id)
