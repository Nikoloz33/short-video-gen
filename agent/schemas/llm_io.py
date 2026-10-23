"""Models the LLM fills in (structured output). Deliberately FLAT (optional fields + enums, lists of
objects, no maps/tuples): Gemini follows flat schemas far more reliably than big unions. Conversion
to the strict VideoSpec happens in code (agent.script), which reports errors back to the model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agent.schemas.video_spec import Audience, Lang, TemplateName

# ---- intake ------------------------------------------------------------------------------------


class IntakeResult(BaseModel):
    in_scope: bool = Field(description="True if the user asks for an instructional/explainer video")
    refusal_reason: str | None = Field(default=None, description="Why the request is out of scope")
    target_lang: Lang | None = Field(default=None, description="Language of the video if stated")
    target_sec: int | None = Field(default=None, description="Requested duration in seconds if stated")
    audience: Audience | None = Field(default=None, description="patient (medical) or workplace (SOP)")
    quiz_count: int | None = Field(default=None, description="Requested number of quiz questions")
    reply: str = Field(description="Short friendly reply to the user, in the user's language")


# ---- plan --------------------------------------------------------------------------------------


class PlanStep(BaseModel):
    title: str
    chunk_ids: list[str] = Field(description="Source chunk ids this step comes from")


class Plan(BaseModel):
    audience: Audience
    goal: str = Field(description="One sentence: what the viewer can do after watching")
    target_sec: int
    steps: list[PlanStep] = Field(description="Ordered outline, 3-8 items")
    quiz_topics: list[str] = Field(default_factory=list, description="What each quiz question checks")
    warnings: list[str] = Field(default_factory=list, description="Hazards/prohibitions to stress")
    summary: str = Field(description="Two-line plan summary for the user")


# ---- script ------------------------------------------------------------------------------------


class DraftRow(BaseModel):
    time: str
    text: str
    icon: str | None = None


class DraftScene(BaseModel):
    template: TemplateName
    narration: str = Field(description="What the voice says in this scene")
    evidence: list[str] = Field(description="Source chunk ids that support every claim in the scene")
    title: str | None = None
    subtitle: str | None = None
    icon: str | None = None
    text: str | None = None
    do_text: str | None = None
    do_icon: str | None = None
    dont_text: str | None = None
    dont_icon: str | None = None
    heading: str | None = None
    items: list[str] | None = None
    label: str | None = None
    seconds: int | None = None
    rows: list[DraftRow] | None = None
    question: str | None = None
    options: list[str] | None = None
    correct_index: int | None = None
    countdown_s: int | None = None
    explanation: str | None = None
    points: list[str] | None = None


class ScriptDraft(BaseModel):
    title: str
    scenes: list[DraftScene]


class SceneRewrite(BaseModel):
    """fix_script / regenerate_scene: replacement scenes keyed by the original scene id."""

    scene_id: str
    scene: DraftScene


class ScriptFix(BaseModel):
    rewrites: list[SceneRewrite]
    note: str = Field(description="One line for the user: what changed and why")


# ---- fact check -------------------------------------------------------------------------------

ClaimKind = Literal["instruction", "fact", "number", "prohibition", "quiz_answer"]


class Claim(BaseModel):
    text: str = Field(description="One atomic, self-contained claim")
    kind: ClaimKind


class Claims(BaseModel):
    claims: list[Claim]


Verdict = Literal["supported", "partially_supported", "unsupported", "contradicts"]


class ClaimVerdict(BaseModel):
    claim_index: int
    verdict: Verdict
    chunk_id: str | None = Field(default=None, description="Chunk the quote comes from")
    quote: str | None = Field(default=None, description="Exact supporting/contradicting span")
    why: str = Field(description="One short line explaining the verdict")


class Verdicts(BaseModel):
    verdicts: list[ClaimVerdict]


class RerankScore(BaseModel):
    chunk_id: str
    score: int = Field(description="0-10 relevance")


class RerankScores(BaseModel):
    scores: list[RerankScore]


# ---- translation -------------------------------------------------------------------------------


class SceneTexts(BaseModel):
    """All human-readable strings of one scene, in scene field order (for translate/back-translate)."""

    scene_id: str
    narration: str
    texts: list[str]


class TranslationResult(BaseModel):
    scenes: list[SceneTexts]
    title: str


# ---- chat editing ------------------------------------------------------------------------------

EditOpName = Literal[
    "set_text",
    "set_icon",
    "reorder",
    "delete_scene",
    "add_scene",
    "set_language",
    "set_voice",
    "set_target_duration",
    "add_quiz",
    "regenerate_scene",
]


class EditOp(BaseModel):
    op: EditOpName
    scene_id: str | None = None
    field: str | None = Field(default=None, description="set_text: narration/title/text/heading/...")
    index: int | None = Field(default=None, description="set_text on a list field: element index")
    value: str | None = Field(default=None, description="set_text: the new text")
    icon: str | None = None
    order: list[str] | None = Field(default=None, description="reorder: all scene ids in new order")
    template: TemplateName | None = Field(default=None, description="add_scene: template")
    after: str | None = Field(default=None, description="add_scene/add_quiz: insert after this scene id")
    language: Lang | None = None
    voice: str | None = None
    target_sec: int | None = None
    instruction: str | None = Field(
        default=None, description="regenerate_scene/add_scene/add_quiz: what to do"
    )


class EditPlan(BaseModel):
    ops: list[EditOp]
    reply: str = Field(description="Short reply to the user describing the change (or why not)")


# ---- privacy -----------------------------------------------------------------------------------


class PiiSpan(BaseModel):
    text: str = Field(description="Exact text to redact, copied from the document")
    kind: Literal["name", "dob", "id", "phone", "address", "email", "mrn", "other"]


class PiiFindings(BaseModel):
    spans: list[PiiSpan]


# ---- transcription -----------------------------------------------------------------------------


class Transcript(BaseModel):
    text: str
