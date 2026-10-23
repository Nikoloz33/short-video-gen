"""A deterministic fake scenario (APP_FAKE=1): responses per role that walk the whole flow for a
handwashing SOP — used by the UI smoke test and for demos without cost."""

from __future__ import annotations

import json
import re
from typing import Any

from agent.llm.types import GenRequest
from agent.schemas.llm_io import (
    Claim,
    Claims,
    ClaimVerdict,
    DraftScene,
    EditOp,
    EditPlan,
    IntakeResult,
    PiiFindings,
    Plan,
    PlanStep,
    SceneRewrite,
    SceneTexts,
    ScriptDraft,
    ScriptFix,
    TranslationResult,
    Verdicts,
)


def _chunks(prompt: str) -> list[str]:
    return re.findall(r"<<<CHUNK (\S+)", prompt) or ["src:1:0"]


def _intake(req: GenRequest) -> IntakeResult:
    msg = req.prompt.split("<<<USER", 1)[-1].lower()
    secs = re.search(r"(\d{2})[- ]?(?:second|sec|s\b|წამ)", msg)
    return IntakeResult(
        in_scope=True,
        target_lang="ka" if ("georgian" in msg or "ქართ" in msg) else "en",
        target_sec=int(secs.group(1)) if secs else 45,
        audience="patient" if "patient" in msg or "discharge" in msg else "workplace",
        quiz_count=1,
        reply="Got it — I'll plan a short training video from your document.",
    )


def _plan(req: GenRequest) -> Plan:
    ids = _chunks(req.prompt)
    return Plan(
        audience="workplace",
        goal="Wash hands correctly before handling food.",
        target_sec=45,
        steps=[PlanStep(title=t, chunk_ids=ids[:2]) for t in ("Wet", "Soap", "Scrub 20 s", "Rinse", "Dry")],
        quiz_topics=["How long to scrub"],
        warnings=["Do not dry hands on the apron"],
        summary="Five steps, one do/don't, one quiz and a summary.",
    )


def _script(req: GenRequest) -> ScriptDraft:
    ev = _chunks(req.prompt)[:3]

    def s(**kw: Any) -> DraftScene:
        return DraftScene(evidence=ev, **kw)

    return ScriptDraft(
        title="Handwashing for food handlers",
        scenes=[
            s(template="title_card", title="How to wash your hands", subtitle="Kitchen hygiene", icon="hand-wash",
              narration="Clean hands stop germs from spreading to food."),
            s(template="step_card", text="Wet your hands with *warm running water*", icon="droplets",
              narration="Step one: wet your hands with warm running water."),
            s(template="step_card", text="Apply *liquid soap*", icon="soap",
              narration="Step two: apply liquid soap from the dispenser."),
            s(template="timer", label="Scrub for at least *20 seconds*", seconds=20, icon="hand-wash",
              narration="Step three: scrub all surfaces of your hands for at least 20 seconds."),
            s(template="step_card", text="Rinse under running water", icon="shower",
              narration="Step four: rinse your hands under running water."),
            s(template="do_dont", do_text="Dry with a *single-use* paper towel", do_icon="wind",
              dont_text="Do not dry your hands on your *apron*", dont_icon="apron",
              narration="Step five: dry with a single-use paper towel. Do not dry your hands on your apron."),
            s(template="quiz_question", question="How long should you scrub?", options=["5 seconds", "At least 20 seconds"],
              correct_index=1, countdown_s=4, narration="Quick quiz: how long should you scrub your hands?"),
            s(template="quiz_answer", explanation="Scrub for at least 20 seconds.",
              narration="The answer: at least 20 seconds."),
            s(template="summary", heading="Clean hands, safe food",
              points=["Wet and apply soap", "Scrub for 20 seconds", "Rinse and dry"],
              narration="Wet, soap, scrub for 20 seconds, rinse and dry with a single-use towel."),
        ],
    )  # fmt: skip


def _claims(req: GenRequest) -> Claims:
    m = re.search(r"Narration: (.*)", req.prompt)
    text = m.group(1).strip() if m else "clean hands"
    return Claims(claims=[Claim(text=text, kind="instruction")])


def _verdicts(req: GenRequest) -> Verdicts:
    claims = re.findall(r"^(\d+)\. \[\w+\] (.*)$", req.prompt, re.M)
    cid = _chunks(req.prompt)[0]
    return Verdicts(
        verdicts=[
            ClaimVerdict(
                claim_index=int(i), verdict="supported", chunk_id=cid, quote=t, why="stated in the SOP"
            )
            for i, t in claims
        ]
    )


def _identity_translation(req: GenRequest) -> TranslationResult:
    m = re.search(r"(\[\s*\{.*\}\s*\])", req.prompt, re.S)
    rows = json.loads(m.group(1)) if m else []
    title = re.search(r"Title: (.*)", req.prompt)
    return TranslationResult(
        scenes=[SceneTexts(scene_id=r["scene_id"], narration=r["narration"], texts=r["texts"]) for r in rows],
        title=title.group(1).strip() if title else "Video",
    )


def _rewrite(req: GenRequest) -> ScriptFix:
    sid = re.search(r"Scene to rewrite: (\S+)", req.prompt)
    target = sid.group(1) if sid else (re.findall(r"^\[(s\d+)\]", req.prompt, re.M) or ["s1"])[0]
    scene = DraftScene(template="step_card", text="Apply *soap*", icon="gloves", narration="Apply liquid soap.",
                       evidence=_chunks(req.prompt)[:1])  # fmt: skip
    return ScriptFix(rewrites=[SceneRewrite(scene_id=target, scene=scene)], note="Shortened the scene.")


def _chat_edit(req: GenRequest) -> EditPlan:
    msg = req.prompt.split("<<<USER", 1)[-1].lower()
    ops: list[EditOp] = []
    step = re.search(r"step (\d+)", msg)
    if "short" in msg and step:
        ops.append(EditOp(op="regenerate_scene", scene_id=f"step {step.group(1)}", instruction="shorter"))
    if "glove" in msg and step:
        ops.append(EditOp(op="set_icon", scene_id=f"step {step.group(1)}", icon="gloves"))
    if "georgian" in msg:
        ops.append(EditOp(op="set_language", language="ka"))
    return EditPlan(ops=ops, reply="Done." if ops else "I can't change that.")


def scenario_responses() -> dict[str, Any]:
    return {
        "intake": _intake,
        "plan": _plan,
        "write_script": _script,
        "claim_extraction": _claims,
        "fact_check_verdict": _verdicts,
        "translate": _identity_translation,
        "back_translation": _identity_translation,
        "fix_script": _rewrite,
        "chat_edit": _chat_edit,
        "pii_scrub": PiiFindings(spans=[]),
        "transcribe": "",
        "rerank": {"scores": []},
    }
