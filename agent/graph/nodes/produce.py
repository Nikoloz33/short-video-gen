"""narrate -> layout_check -> render_preview / render_final -> validate_video -> done."""

from __future__ import annotations

import contextvars
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from agent.graph.deps import Deps, emit, say, status
from agent.graph.nodes.common import dump, spec_of
from agent.graph.state import GraphState
from agent.llm.usage import Usage, merge_usage
from agent.metrics import record_render
from agent.render.validate import validate_video
from agent.render.worker import Preset, RenderError
from agent.script import apply_audio
from agent.tts.narrator import NarrationError

#: Parallel TTS requests (Gemini TTS quota is low per minute; the router backs off on 429).
TTS_WORKERS = 3


def make_narrate(deps: Deps) -> Any:
    def narrate(state: GraphState) -> dict[str, Any]:
        spec = spec_of(state)
        usage = Usage()
        hits = synthesized = 0
        t0 = time.time()
        todo = [s for s in spec.scenes if s.audio is None]
        clips: dict[str, Any] = {}
        failures: list[str] = []

        def one(scene: Any) -> tuple[str, Any, Usage]:
            clip, u = deps.narrator.synth(scene.narration.replace("*", ""), spec.lang, spec.voice)
            return scene.id, clip, u

        # A few clips at a time: much faster than one by one, gentle on the low TTS quota. Each worker
        # runs in a copy of this context so the spend budget and thread id follow the calls.
        ctx = contextvars.copy_context()
        with ThreadPoolExecutor(max_workers=TTS_WORKERS) as pool:
            futures = {pool.submit(ctx.copy().run, one, s): s.id for s in todo}
            for fut in as_completed(futures):
                try:
                    sid, clip, u = fut.result()
                except NarrationError as e:
                    failures.append(f"scene {futures[fut]}: {e}")
                    continue
                clips[sid] = clip
                usage = merge_usage(usage, u)
                hits += clip.cache_hit
                synthesized += not clip.cache_hit
                emit({"type": "render_progress", "stage": "tts", "done": len(clips), "total": len(todo),
                      "cache_hits": hits, "elapsedMs": int((time.time() - t0) * 1000)})  # fmt: skip
        if failures:
            # Raise instead of ending the run: the checkpoint stays on this node, so Retry resumes here
            # and every clip already made comes back from the cache.
            raise NarrationError(f"Narration failed for {'; '.join(failures)}. Press Retry to try again.")
        scenes = [
            apply_audio(s, clips[s.id].path.relative_to(deps.media_root).as_posix(), clips[s.id].duration_s)
            if s.id in clips
            else s
            for s in spec.scenes
        ]
        out = spec.model_copy(update={"scenes": scenes})
        deps.projects.save_spec(state["project_id"], out)
        stats = {"clips": len(spec.scenes), "synthesized": synthesized, "cache_hits": hits + (len(spec.scenes) - len(todo)),
                 "ms": int((time.time() - t0) * 1000)}  # fmt: skip
        return {
            **status("checking_layout"),
            "spec": dump(out),
            "tts_stats": stats,
            "usage": usage.model_dump(),
        }

    return narrate


def make_layout_check(deps: Deps) -> Any:
    def layout_check(state: GraphState) -> dict[str, Any]:
        spec = spec_of(state)
        app = deps.app
        issues = deps.renderer.check(spec, {"minTotalS": app.min_duration_s, "maxTotalS": app.max_duration_s})
        if not issues:
            return {"layout_issues": [], "route": "render_preview", **status("rendering_preview")}
        card = {"kind": "layout", "issues": issues}
        if state.get("layout_loops", 0) < 2:
            return {**say(f"Layout check found {len(issues)} issue(s); fixing them.", card),
                    "layout_issues": issues, "route": "fix_script", "layout_loops": state.get("layout_loops", 0) + 1}  # fmt: skip
        return {**say("The script still does not fit the video layout. Please shorten it in chat.", card),
                "layout_issues": issues, "route": "end", **status("needs_attention")}  # fmt: skip

    return layout_check


def _render(deps: Deps, state: GraphState, preset: Preset) -> dict[str, Any]:
    spec = spec_of(state)
    out_dir = deps.projects.version_dir(state["project_id"], spec.version) / preset
    t0 = time.time()

    def forward(ev: dict[str, Any]) -> None:
        emit({"type": "render_progress", "preset": preset, "version": spec.version,
              "tts": state.get("tts_stats", {}), **{k: v for k, v in ev.items() if k != "type"}})  # fmt: skip

    try:
        result = deps.renderer.render(spec, preset, out_dir, deps.media_root, forward)
    except RenderError as e:
        return {
            **say(f"Rendering failed ({e.code}): {e}"),
            **status("error"),
            "route": "end",
            "error": str(e),
        }
    result["wall_ms"] = int((time.time() - t0) * 1000)
    emit({"type": "render_done", "preset": preset, "version": spec.version, "stages": result.get("stages", {}),
          "durationMs": result.get("durationMs"), "totalFrames": result.get("totalFrames"),
          "cacheHits": result.get("cacheHits", {}), "tts": state.get("tts_stats", {})})  # fmt: skip
    render = dict(state.get("render") or {})
    if render.get("version") != spec.version:
        render = {}
    render.update({preset: result, "last": preset, "version": spec.version})
    return {"render": render, "route": "validate_video"}


def make_render_preview(deps: Deps) -> Any:
    def render_preview(state: GraphState) -> dict[str, Any]:
        return {**status("rendering_preview"), **_render(deps, state, "preview")}

    return render_preview


def make_render_final(deps: Deps) -> Any:
    def render_final(state: GraphState) -> dict[str, Any]:
        return {**status("rendering_final"), **_render(deps, state, "final")}

    return render_final


def make_validate_video(deps: Deps) -> Any:
    def validate(state: GraphState) -> dict[str, Any]:
        spec = spec_of(state)
        render = dict(state["render"])
        preset: Preset = render["last"]
        checks = validate_video(spec, preset, render[preset], deps.settings.ffmpeg("ffprobe"))
        render[preset] = {**render[preset], "checks": checks}
        failed = [c for c in checks if not c["ok"]]
        record_render(deps.settings.data_dir / "metrics.db", state["project_id"], spec.version, preset,
                      spec.total_s, render[preset], state.get("tts_stats") or {}, not failed)  # fmt: skip
        out: dict[str, Any] = {"render": render}
        if failed:
            card = {"kind": "validation", "preset": preset, "checks": checks}
            return {**out, **say(f"Video validation failed: {', '.join(c['name'] for c in failed)}.", card),
                    **status("needs_attention"), "route": "end"}  # fmt: skip
        return {**out, "route": "present_video" if preset == "preview" else "done"}

    return validate


def make_done(deps: Deps) -> Any:
    def done(state: GraphState) -> dict[str, Any]:
        r = state["render"]
        usage = state.get("usage") or {}
        cost = sum(x.get("cost_usd", 0.0) for x in usage.get("roles", []))
        final = r.get("final", {})
        card = {"kind": "done", "version": r.get("version"), "files": {k: Path(final[k]).name for k in ("mp4", "srt", "vtt", "quiz") if k in final},
                "cost_usd": round(cost, 4), "usage": usage.get("roles", []), "checks": final.get("checks", [])}  # fmt: skip
        return {**say(f"Final video v{r.get('version')} is ready. Total model cost: ${cost:.3f}.", card),
                **status("done")}  # fmt: skip

    return done
