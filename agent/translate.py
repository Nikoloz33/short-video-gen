"""Translate a fact-checked spec, then back-translate (Flash) and rerun the deterministic gates."""

from __future__ import annotations

import json

from agent.factcheck.gates import check_translation
from agent.factcheck.normalize import glossary
from agent.llm.router import LLMRouter
from agent.llm.usage import Usage, merge_usage
from agent.prompts import load_prompt
from agent.schemas.llm_io import SceneTexts, TranslationResult
from agent.schemas.video_spec import Lang, VideoSpec
from agent.script import scene_texts, with_scene_texts

LANG_NAME = {"ka": "Georgian", "en": "English"}


def _payload(spec: VideoSpec) -> str:
    rows = [{"scene_id": s.id, "narration": s.narration, "texts": scene_texts(s)} for s in spec.scenes]
    return json.dumps(rows, ensure_ascii=False, indent=1)


def _glossary(source: Lang, target: Lang) -> str:
    return "\n".join(f"- {' / '.join(t[source])} = {' / '.join(t[target])}" for t in glossary())


def translate_spec(
    spec: VideoSpec, target: Lang, router: LLMRouter
) -> tuple[VideoSpec, dict[str, list[str]], Usage]:
    """Returns (translated spec, problems per scene id, usage)."""
    if spec.lang == target:
        return spec, {}, Usage()
    src = spec.lang
    tr = router.structured(
        "translate",
        load_prompt("translate").render(
            source_name=LANG_NAME[src],
            target_name=LANG_NAME[target],
            glossary=_glossary(src, target),
            scenes=_payload(spec),
            title=spec.title,
        ),
        TranslationResult,
    )
    usage = tr.usage
    by_id: dict[str, SceneTexts] = {s.scene_id: s for s in tr.value.scenes}
    problems: dict[str, list[str]] = {}
    scenes = []
    for s in spec.scenes:
        t = by_id.get(s.id)
        if t is None or len(t.texts) != len(scene_texts(s)):
            problems[s.id] = ["translation missing or has a different number of texts"]
            scenes.append(s)
            continue
        scenes.append(with_scene_texts(s, t.narration, t.texts).model_copy(update={"audio": None}))
    out = spec.model_copy(
        update={"lang": target, "title": tr.value.title[:140] or spec.title, "scenes": scenes}
    )

    back = router.structured(
        "back_translation",
        load_prompt("back_translate").render(
            from_name=LANG_NAME[target], to_name=LANG_NAME[src], scenes=_payload(out), title=out.title
        ),
        TranslationResult,
    )
    usage = merge_usage(usage, back.usage)
    back_by_id = {s.scene_id: s for s in back.value.scenes}
    for orig, new in zip(spec.scenes, out.scenes, strict=True):
        if orig.id in problems:
            continue
        b = back_by_id.get(orig.id)
        o_texts = [orig.narration, *scene_texts(orig)]
        n_texts = [new.narration, *scene_texts(new)]
        b_texts = [b.narration, *b.texts] if b else ["" for _ in o_texts]
        found: list[str] = []
        for o, n, bt in zip(o_texts, n_texts, b_texts + [""] * (len(o_texts) - len(b_texts)), strict=False):
            found += check_translation(o, n, bt)
        if found:
            problems[orig.id] = sorted(set(found))
    return out, problems, usage
