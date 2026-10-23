"""Script helpers: LLM draft -> strict VideoSpec, duration estimates, per-scene text access.

Everything here is deterministic. Timing estimates only size the script before TTS; once clips are
measured, `apply_audio` sets real durations.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ValidationError

from agent.config import Language, load_app
from agent.schemas.llm_io import DraftScene, ScriptDraft
from agent.schemas.video_spec import Audience, AudioClip, Lang, Scene, SourceRef, VideoSpec

LEAD_IN_S = 0.3
TAIL_S = 0.7
MAX_SCENE_S = 15.0

# Minimum on-screen time per template (reading time of the visuals, before narration is measured).
_MIN_S: dict[str, float] = {
    "title_card": 3.5,
    "step_card": 3.5,
    "do_dont": 5.0,
    "checklist": 3.0,
    "warning": 4.0,
    "timer": 4.0,
    "schedule": 3.5,
    "quiz_question": 4.0,
    "quiz_answer": 4.0,
    "summary": 3.5,
    "disclaimer": 5.0,
}

# Text fields of each template, in display order (list fields expanded per element).
TEXT_FIELDS: dict[str, tuple[str, ...]] = {
    "title_card": ("title", "subtitle"),
    "step_card": ("text",),
    "do_dont": ("do_text", "dont_text"),
    "checklist": ("heading", "items"),
    "warning": ("heading", "text"),
    "timer": ("label",),
    "schedule": ("heading", "rows"),
    "quiz_question": ("question", "options"),
    "quiz_answer": ("question", "options", "explanation"),
    "summary": ("heading", "points"),
    "disclaimer": ("heading", "text"),
}


def pace(lang: Language) -> float:
    return load_app().languages[lang].chars_per_sec


def min_scene_s(scene: Scene) -> float:
    base = _MIN_S[scene.template]
    n = len(
        getattr(scene, "items", None) or getattr(scene, "points", None) or getattr(scene, "rows", None) or []
    )
    return base + 0.8 * n


def scene_duration(scene: Scene, speech_s: float) -> float:
    """Scene length from the (measured or estimated) narration length."""
    d = max(min_scene_s(scene), LEAD_IN_S + speech_s + TAIL_S)
    if scene.template == "quiz_question":
        d = max(d, LEAD_IN_S + speech_s + 0.5) + scene.countdown_s
    return round(min(d, MAX_SCENE_S + (scene.countdown_s if scene.template == "quiz_question" else 0)), 2)


def estimate_speech_s(text: str, lang: Language) -> float:
    return len(text) / pace(lang)


def narration_budget_chars(target_sec: float, lang: Language) -> int:
    """How many narration characters fit a video of `target_sec` (≈80 % of the time is speech)."""
    return int(target_sec * 0.8 * pace(lang))


def scene_texts(scene: Scene) -> list[str]:
    out: list[str] = []
    for f in TEXT_FIELDS[scene.template]:
        v = getattr(scene, f, None)
        if v is None:
            continue
        if f == "rows":
            for r in v:
                out += [r.time, r.text]
        elif isinstance(v, list):
            out += list(v)
        else:
            out.append(v)
    return out


def with_scene_texts(scene: Scene, narration: str, texts: list[str]) -> Scene:
    """Returns `scene` with its narration and display texts replaced (same order as scene_texts)."""
    data = scene.model_dump()
    data["narration"] = narration
    it = iter(texts)
    for f in TEXT_FIELDS[scene.template]:
        v = data.get(f)
        if v is None:
            continue
        if f == "rows":
            for r in v:
                r["time"] = next(it, r["time"])
                r["text"] = next(it, r["text"])
        elif isinstance(v, list):
            data[f] = [next(it, x) for x in v]
        else:
            data[f] = next(it, v)
    return type(scene).model_validate(data)


_DEFAULT_ICON = {
    "step_card": "check",
    "warning": "alert",
    "timer": "timer",
    "do_dont": "check",
    "title_card": "info",
}
_REQUIRED_ICONS = {
    "step_card": ("icon",),
    "warning": ("icon",),
    "timer": ("icon",),
    "do_dont": ("do_icon", "dont_icon"),
}


def _guess_icon(text: str, template: str) -> str:
    """Best catalog match for the scene's words (models sometimes omit or invent icons)."""
    from agent.catalog import search_icons

    for word in sorted(re.findall(r"[^\W\d_]{4,}", text.lower()), key=len, reverse=True):
        hits = search_icons(word)
        if hits:
            return hits[0]
    return _DEFAULT_ICON.get(template, "info")


def _fill_defaults(d: DraftScene) -> DraftScene:
    """Deterministic repairs for gaps the model leaves: unknown/missing icons, missing short texts."""
    from agent.catalog import icon_names

    data = d.model_dump()
    known = icon_names()
    words = " ".join(str(v) for v in (d.text, d.heading, d.label, d.do_text, d.dont_text, d.narration) if v)
    for f in _REQUIRED_ICONS.get(d.template, ()):
        if not data.get(f) or data[f] not in known:
            src = (
                data.get("dont_text")
                if f == "dont_icon"
                else data.get("do_text")
                if f == "do_icon"
                else words
            )
            data[f] = _guess_icon(src or words, d.template)
    if data.get("icon") and data["icon"] not in known:
        data["icon"] = _guess_icon(words, d.template)
    if data.get("rows"):
        for r in data["rows"]:
            if r.get("icon") and r["icon"] not in known:
                r["icon"] = None
    # Missing texts are filled by _coerce_fields (synonym fields first, then the narration).
    return DraftScene.model_validate(data)


# Where to take a required text from when the model filled a sibling field instead (seen live:
# "warning.title", "disclaimer.explanation", "summary.items").
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "title": ("heading", "text", "label"),
    "heading": ("title", "label", "text", "question"),
    "text": ("subtitle", "explanation", "label", "heading", "title"),
    "label": ("text", "heading", "title"),
    "question": ("text", "heading", "title"),
    "explanation": ("text", "subtitle"),
    "items": ("points", "options"),
    "points": ("items", "options"),
    "options": ("items", "points"),
}
_LIST_LIMITS = {"items": 5, "points": 4, "options": 4, "rows": 5}
NARRATION_MAX = 400
TEXT_MAX = 140


def _clip(text: str, limit: int) -> str:
    """Shortens at a sentence (or word) boundary; never mid-word."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in (". ", "! ", "? ", "; ", ", ", " "):
        at = cut.rfind(sep)
        if at > limit // 2:
            return cut[: at + (1 if sep.strip() else 0)].strip()
    return cut.strip()


def _template_fields(template: str) -> dict[str, Any]:
    from agent.schemas import video_spec as vs

    models: dict[str, type[BaseModel]] = {
        "title_card": vs.TitleCardScene, "step_card": vs.StepCardScene, "do_dont": vs.DoDontScene,
        "checklist": vs.ChecklistScene, "warning": vs.WarningScene, "timer": vs.TimerScene,
        "schedule": vs.ScheduleScene, "quiz_question": vs.QuizQuestionScene, "quiz_answer": vs.QuizAnswerScene,
        "summary": vs.SummaryScene, "disclaimer": vs.DisclaimerScene,
    }  # fmt: skip
    cls = models[template]
    return dict(cls.model_fields)


def _coerce_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Keeps only the template's own fields, fills required ones from synonyms, clamps lengths."""
    fields = _template_fields(str(data["template"]))
    out = {k: v for k, v in data.items() if k in fields}
    for name, info in fields.items():
        if out.get(name) not in (None, "", []):
            continue
        for alt in _SYNONYMS.get(name, ()):
            if data.get(alt) not in (None, "", []):
                out[name] = data[alt]
                break
        if (
            out.get(name) in (None, "", [])
            and info.is_required()
            and name in ("text", "heading", "label", "title")
        ):
            out[name] = re.split(r"(?<=[.!?])\s", str(data.get("narration", "")).strip())[0]
    for name, limit in _LIST_LIMITS.items():
        if isinstance(out.get(name), list):
            out[name] = out[name][:limit]
    for name, value in list(out.items()):
        if isinstance(value, str) and name not in (
            "narration",
            "id",
            "template",
            "icon",
            "do_icon",
            "dont_icon",
        ):
            out[name] = _clip(value, 300 if name == "text" and data["template"] == "disclaimer" else TEXT_MAX)
        elif isinstance(value, list) and value and isinstance(value[0], str):
            out[name] = [_clip(v, TEXT_MAX) for v in value]
    out["narration"] = _clip(str(data.get("narration", "")), NARRATION_MAX)
    return out


def _scene_dict(d: DraftScene, sid: str) -> dict[str, Any]:
    d = _fill_defaults(d)
    data = {k: v for k, v in d.model_dump().items() if v is not None}
    if d.rows is not None:
        data["rows"] = [r.model_dump() for r in d.rows]
    data = _coerce_fields(data)
    data["id"] = sid
    data["duration_s"] = 5.0
    data["audio"] = None
    return data


class DraftError(ValueError):
    """The draft cannot become a valid spec; `problems` are fed back to the model."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def draft_scenes(drafts: list[DraftScene], lang: Lang, start_index: int = 1) -> list[Scene]:
    """Converts flat LLM scenes to strict scene models (ids s<N>, step numbering, quiz defaults)."""
    from pydantic import TypeAdapter

    adapter: TypeAdapter[Scene] = TypeAdapter(Scene)
    total_steps = sum(1 for d in drafts if d.template == "step_card")
    step = 0
    last_q: DraftScene | None = None
    out: list[Scene] = []
    problems: list[str] = []
    for i, d in enumerate(drafts):
        data = _scene_dict(d, f"s{start_index + i}")
        if d.template == "step_card":
            step += 1
            data["step_no"], data["total_steps"] = step, max(total_steps, step)
        if d.template == "quiz_question":
            data.setdefault("countdown_s", 5)
            last_q = d
        if d.template == "quiz_answer" and last_q is not None:
            for f in ("question", "options", "correct_index"):
                data.setdefault(f, getattr(last_q, f))
        try:
            scene = adapter.validate_python(data)
        except ValidationError as e:
            errs = "; ".join(f"{'.'.join(str(p) for p in x['loc'])}: {x['msg']}" for x in e.errors()[:6])
            problems.append(f"scene {i + 1} ({d.template}): {errs}")
            continue
        out.append(
            scene.model_copy(
                update={"duration_s": scene_duration(scene, estimate_speech_s(scene.narration, lang))}
            )
        )
    if problems:
        raise DraftError(problems)
    return out


def draft_to_spec(
    draft: ScriptDraft,
    *,
    lang: Lang,
    source_lang: Lang,
    audience: Audience,
    target_sec: float,
    sources: list[SourceRef],
    voice: str = "Kore",
    theme: str = "default",
    version: int = 1,
) -> VideoSpec:
    scenes = draft_scenes(draft.scenes, lang)
    try:
        return VideoSpec(
            version=version,
            title=draft.title[:140] or "Instructions",
            lang=lang,
            source_lang=source_lang,
            audience=audience,
            voice=voice,
            theme=theme,
            target_sec=min(90, max(15, target_sec)),
            scenes=scenes,
            sources=sources,
        )
    except ValidationError as e:
        raise DraftError([f"{'.'.join(str(p) for p in x['loc'])}: {x['msg']}" for x in e.errors()[:6]]) from e


def renumber(spec: VideoSpec) -> VideoSpec:
    """Re-derives step numbers after reorders/deletes/inserts."""
    steps = [s for s in spec.scenes if s.template == "step_card"]
    scenes: list[Scene] = []
    n = 0
    for s in spec.scenes:
        if s.template == "step_card":
            n += 1
            s = s.model_copy(update={"step_no": n, "total_steps": len(steps)})
        scenes.append(s)
    return spec.model_copy(update={"scenes": scenes})


def apply_audio(scene: Scene, src: str, duration_s: float) -> Scene:
    clip = AudioClip(src=src, duration_s=round(duration_s, 3), start_s=LEAD_IN_S)
    return scene.model_copy(update={"audio": clip, "duration_s": scene_duration(scene, duration_s)})


def next_scene_id(spec: VideoSpec) -> str:
    nums = [int(s.id[1:]) for s in spec.scenes if s.id[:1] == "s" and s.id[1:].isdigit()]
    return f"s{max(nums, default=0) + 1}"


def outline(spec: VideoSpec) -> str:
    """Compact human/LLM readable view of a spec (ids, templates, texts, narration)."""
    lines = [f"title: {spec.title} | lang: {spec.lang} | {spec.total_s:.1f} s"]
    for s in spec.scenes:
        texts = " / ".join(scene_texts(s))
        icon = getattr(s, "icon", None)
        lines.append(
            f"[{s.id}] {s.template}{f' icon={icon}' if icon else ''}: {texts} || says: {s.narration}"
        )
    return "\n".join(lines)
