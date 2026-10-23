"""chat_edit (Flash -> EditPlan of typed ops) and apply_edit (deterministic, minimal recompute).

Recompute rules:
- text / regenerate / add scene / add quiz -> fact-check those scenes -> TTS those scenes -> render
- language change -> translate -> TTS all -> render
- voice change -> TTS all -> render
- icon / reorder / delete -> render only
- target duration -> new script
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import ValidationError

from agent.catalog import icon_names
from agent.graph.deps import Deps, say, status
from agent.graph.nodes.common import chunks_block, dump, icons_block, last_user_text, spec_of
from agent.graph.nodes.script import LANG_NAME
from agent.graph.state import RESET, GraphState
from agent.llm.usage import Usage, merge_usage
from agent.prompts import load_prompt
from agent.schemas.llm_io import EditOp, EditPlan, ScriptFix
from agent.schemas.video_spec import Scene, VideoSpec
from agent.script import draft_scenes, next_scene_id, outline, renumber

VOICES = {"Kore", "Puck", "Charon", "Aoede", "Fenrir", "Leda", "Orus", "Zephyr"}
LIST_FIELDS = {"items", "options", "points"}


class EditError(ValueError):
    pass


def make_chat_edit(deps: Deps) -> Any:
    def chat_edit(state: GraphState) -> dict[str, Any]:
        spec = spec_of(state)
        r = deps.router.structured(
            "chat_edit",
            load_prompt("chat_edit").render(
                icons=icons_block(), outline=outline(spec), message=last_user_text(state)
            ),
            EditPlan,
        )
        return {"edit": r.value.model_dump(), "usage": r.usage.model_dump(), **status("editing")}

    return chat_edit


def _step_scene_id(spec: VideoSpec, ref: str) -> str:
    """Accepts real ids and 'step N' references."""
    if any(s.id == ref for s in spec.scenes):
        return ref
    low = ref.lower().replace("step", "").strip()
    if low.isdigit():
        steps = [s for s in spec.scenes if s.template == "step_card"]
        n = int(low)
        if 1 <= n <= len(steps):
            return steps[n - 1].id
    raise EditError(f"there is no scene {ref!r}")


def _regenerate(
    deps: Deps, state: GraphState, spec: VideoSpec, scene_id: str, instruction: str
) -> tuple[list[Scene], Usage]:
    r = deps.router.structured(
        "fix_script",
        load_prompt("regenerate_scene").render(
            lang_name=LANG_NAME[spec.lang],
            instruction=instruction,
            outline=outline(spec),
            scene_id=scene_id,
            chunks=chunks_block(deps.store(state["project_id"]).chunks()),
            icons=icons_block(),
        ),
        ScriptFix,
    )
    return draft_scenes([rw.scene for rw in r.value.rewrites], spec.lang), r.usage


def apply_ops(
    deps: Deps, state: GraphState, spec: VideoSpec, ops: list[EditOp]
) -> tuple[VideoSpec, dict[str, Any], Usage]:
    """Returns (new spec, effects, usage). effects: fact_targets, retranslate, rewrite, notes."""
    scenes: list[Scene] = list(spec.scenes)
    effects: dict[str, Any] = {"fact_targets": [], "retranslate": None, "rewrite": None, "notes": []}
    usage = Usage()
    voice, lang = spec.voice, spec.lang

    def idx(sid: str) -> int:
        real = _step_scene_id(spec.model_copy(update={"scenes": scenes}), sid)
        return next(i for i, s in enumerate(scenes) if s.id == real)

    for op in ops:
        if op.op == "set_text":
            if not op.scene_id or not op.field or op.value is None:
                raise EditError("set_text needs scene_id, field and value")
            i = idx(op.scene_id)
            data = scenes[i].model_dump()
            if op.field not in data or op.field in ("id", "template", "evidence", "audio", "duration_s"):
                raise EditError(f"scene {scenes[i].id} has no editable field {op.field!r}")
            if op.field in LIST_FIELDS:
                if op.index is None or not 0 <= op.index < len(data[op.field]):
                    raise EditError(f"{op.field} needs a valid index")
                data[op.field][op.index] = op.value
            else:
                data[op.field] = op.value
            data["audio"] = None if op.field == "narration" else data["audio"]
            try:
                scenes[i] = type(scenes[i]).model_validate(data)
            except ValidationError as e:
                raise EditError(f"invalid value: {e.errors()[0]['msg']}") from e
            effects["fact_targets"].append(scenes[i].id)
        elif op.op == "set_icon":
            if not op.scene_id or not op.icon:
                raise EditError("set_icon needs scene_id and icon")
            if op.icon not in icon_names():
                raise EditError(f"icon {op.icon!r} is not in the catalog")
            i = idx(op.scene_id)
            field = op.field if op.field in ("icon", "do_icon", "dont_icon") else "icon"
            if field not in scenes[i].model_dump():
                raise EditError(f"scene {scenes[i].id} has no {field}")
            scenes[i] = scenes[i].model_copy(update={field: op.icon})
        elif op.op == "reorder":
            order = op.order or []
            if sorted(order) != sorted(s.id for s in scenes):
                raise EditError("reorder must list every scene id exactly once")
            by_id = {s.id: s for s in scenes}
            scenes = [by_id[i] for i in order]
        elif op.op == "delete_scene":
            if not op.scene_id:
                raise EditError("delete_scene needs scene_id")
            del scenes[idx(op.scene_id)]
            if not scenes:
                raise EditError("cannot delete the last scene")
        elif op.op in ("add_scene", "add_quiz"):
            after = idx(op.after) if op.after else len(scenes) - 1
            instruction = op.instruction or ""
            if op.op == "add_quiz":
                instruction = f"Write a quiz_question scene followed by its quiz_answer scene. {instruction}"
            elif op.template:
                instruction = f"Write one {op.template} scene. {instruction}"
            new, u = _regenerate(deps, state, spec.model_copy(update={"scenes": scenes}), "new", instruction)
            usage = merge_usage(usage, u)
            cur = spec.model_copy(update={"scenes": scenes})
            for k, s in enumerate(new):
                sid = next_scene_id(cur)
                s = s.model_copy(update={"id": sid, "audio": None})
                scenes.insert(after + 1 + k, s)
                cur = spec.model_copy(update={"scenes": scenes})
                effects["fact_targets"].append(sid)
        elif op.op == "regenerate_scene":
            if not op.scene_id:
                raise EditError("regenerate_scene needs scene_id")
            i = idx(op.scene_id)
            new, u = _regenerate(
                deps, state, spec.model_copy(update={"scenes": scenes}), scenes[i].id, op.instruction or ""
            )
            usage = merge_usage(usage, u)
            if not new:
                raise EditError("the rewrite came back empty")
            scenes[i] = new[0].model_copy(update={"id": scenes[i].id, "audio": None})
            effects["fact_targets"].append(scenes[i].id)
        elif op.op == "set_language":
            if op.language not in ("ka", "en"):
                raise EditError("only Georgian (ka) and English (en) are supported")
            effects["retranslate"] = op.language
        elif op.op == "set_voice":
            if op.voice not in VOICES:
                raise EditError(f"unknown voice {op.voice!r}; choose one of {', '.join(sorted(VOICES))}")
            voice = op.voice
            scenes = [s.model_copy(update={"audio": None}) for s in scenes]
        elif op.op == "set_target_duration":
            if not op.target_sec or not 30 <= op.target_sec <= 300:
                raise EditError("target duration must be between 30 seconds and 5 minutes")
            effects["rewrite"] = op.target_sec
    new_spec = renumber(spec.model_copy(update={"scenes": scenes, "voice": voice, "lang": lang}))
    VideoSpec.model_validate(new_spec.model_dump())
    effects["fact_targets"] = list(dict.fromkeys(effects["fact_targets"]))
    return new_spec, effects, usage


def _back_to_review(state: GraphState) -> str:
    """Nothing changed: return to the review the user was in (or finish if there was none)."""
    if state.get("render") and state.get("script_approved"):
        return "present_video"
    return "present_script" if state.get("spec") else "end"


def make_apply_edit(deps: Deps) -> Any:
    def apply_edit(state: GraphState) -> dict[str, Any]:
        spec = spec_of(state)
        plan = EditPlan.model_validate(state.get("edit") or {"ops": [], "reply": ""})
        if not plan.ops:
            return {
                **say(plan.reply or "I didn't find anything to change."),
                "route": _back_to_review(state),
                "edit": None,
            }
        try:
            new_spec, effects, usage = apply_ops(deps, state, spec, plan.ops)
        except (EditError, ValidationError) as e:
            return {**say(f"I couldn't apply that: {e}"), "route": _back_to_review(state), "edit": None}
        if effects["rewrite"]:
            req = {**state.get("request", {}), "target_sec": effects["rewrite"]}
            return {**say(plan.reply), "request": req, "route": "write_script", "edit": None,
                    "usage": usage.model_dump()}  # fmt: skip
        new_spec = new_spec.model_copy(update={"version": spec.version + 1})
        deps.projects.save_spec(state["project_id"], new_spec)
        out: dict[str, Any] = {
            **say(
                plan.reply,
                {
                    "kind": "edit",
                    "version": new_spec.version,
                    "ops": [o.model_dump(exclude_none=True) for o in plan.ops],
                },
            ),
            "spec": dump(new_spec),
            "edit": None,
            "usage": usage.model_dump(),
            "versions": [{"version": new_spec.version, "note": plan.reply[:120], "created": time.time()}],
            "fix_loops": 0,
            "last_signature": "",
        }
        if effects["retranslate"]:
            req = {**state.get("request", {}), "target_lang": effects["retranslate"]}
            return {**out, "request": req, "route": "translate", **status("translating")}
        if effects["fact_targets"]:
            return {
                **out,
                "fact_targets": effects["fact_targets"],
                "scene_reports": [RESET],
                "route": "fact_check",
            }
        if state.get("script_approved"):
            return {**out, "route": "narrate"}
        return {**out, "route": "present_script"}

    return apply_edit
