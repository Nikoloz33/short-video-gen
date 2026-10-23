"""Client for the render worker: one JSON request on stdin, JSON-lines events on stdout.

`Renderer` is the protocol the graph uses; `RenderWorker` spawns Node, `FakeRenderer` makes a tiny
MP4 with ffmpeg (testsrc + sine) so tests and fake mode never need Chromium.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol

from agent.logging import get_logger
from agent.schemas.video_spec import VideoSpec

log = get_logger("render")
Preset = Literal["preview", "final"]
OnEvent = Callable[[dict[str, Any]], None]


class RenderError(RuntimeError):
    def __init__(self, code: str, message: str, issues: list[dict[str, Any]] | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.issues = issues or []


class Renderer(Protocol):
    def check(self, spec: VideoSpec, limits: dict[str, float] | None = None) -> list[dict[str, Any]]: ...

    def render(
        self, spec: VideoSpec, preset: Preset, out_dir: Path, media_root: Path, on_event: OnEvent
    ) -> dict[str, Any]: ...


class RenderWorker:
    def __init__(
        self, repo_root: Path, node: str = "node", timeout_s: int = 900, concurrency: int | None = None
    ):
        self.repo_root = repo_root
        self.node = node
        self.timeout_s = timeout_s
        self.concurrency = concurrency
        self.cli = repo_root / "node_modules" / "tsx" / "dist" / "cli.mjs"
        self.script = repo_root / "video" / "scripts" / "render-worker.ts"

    def _run(self, request: dict[str, Any], on_event: OnEvent | None) -> dict[str, Any]:
        # node + tsx's cli.mjs directly (no shell): the repo path may contain spaces.
        proc = subprocess.Popen(
            [self.node, str(self.cli), str(self.script)],
            cwd=self.repo_root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        assert proc.stdin and proc.stdout
        proc.stdin.write(json.dumps(request, ensure_ascii=False))
        proc.stdin.close()
        last: dict[str, Any] = {}
        deadline = time.monotonic() + self.timeout_s + 30
        for line in proc.stdout:
            if time.monotonic() > deadline:
                proc.kill()
                raise RenderError("timeout", "render worker did not finish in time")
            line = line.strip()
            if not line.startswith("{"):
                continue
            event = json.loads(line)
            last = event
            if event.get("type") == "progress" and on_event:
                on_event(event)
        proc.wait()
        stderr = proc.stderr.read() if proc.stderr else ""
        if last.get("type") == "error":
            raise RenderError(str(last.get("code")), str(last.get("message")), last.get("issues"))
        if last.get("type") not in ("done", "check"):
            raise RenderError("worker_crashed", stderr[-2000:] or f"exit code {proc.returncode}")
        return last

    def check(self, spec: VideoSpec, limits: dict[str, float] | None = None) -> list[dict[str, Any]]:
        req: dict[str, Any] = {"cmd": "check", "spec": spec.model_dump(mode="json")}
        if limits:
            req["limits"] = limits
        try:
            res = self._run(req, None)
        except RenderError as e:
            if e.code == "invalid_spec":
                return [{"scene_id": "-", "field": "spec", "code": "invalid_spec", "message": str(e)}]
            raise
        issues: list[dict[str, Any]] = res.get("issues", [])
        return issues

    def render(
        self, spec: VideoSpec, preset: Preset, out_dir: Path, media_root: Path, on_event: OnEvent
    ) -> dict[str, Any]:
        req: dict[str, Any] = {
            "cmd": "render",
            "spec": spec.model_dump(mode="json"),
            "preset": preset,
            "out_dir": str(out_dir),
            "media_root": str(media_root),
            "timeout_s": self.timeout_s,
        }
        if self.concurrency:
            req["concurrency"] = self.concurrency
        return self._run(req, on_event)


def _stamp(x: float, sep: str) -> str:
    ms = round(x * 1000)
    return f"{ms // 3600000:02}:{ms % 3600000 // 60000:02}:{ms % 60000 // 1000:02}{sep}{ms % 1000:03}"


class FakeRenderer:
    """Writes a tiny but valid MP4 (testsrc + sine) at the preset size, plus captions + quiz.json."""

    SIZES: ClassVar[dict[str, tuple[int, int, int]]] = {"preview": (540, 960, 15), "final": (1080, 1920, 30)}

    def __init__(self, ffmpeg: Path, check_issues: list[dict[str, Any]] | None = None) -> None:
        self.ffmpeg = ffmpeg
        self.check_issues = check_issues or []
        self.renders: list[tuple[int, str]] = []

    def check(self, spec: VideoSpec, limits: dict[str, float] | None = None) -> list[dict[str, Any]]:
        return list(self.check_issues)

    def render(
        self, spec: VideoSpec, preset: Preset, out_dir: Path, media_root: Path, on_event: OnEvent
    ) -> dict[str, Any]:
        self.renders.append((spec.version, preset))
        w, h, fps = self.SIZES[preset]
        dur = spec.total_s
        total = round(dur * fps)
        out_dir.mkdir(parents=True, exist_ok=True)
        mp4 = out_dir / "video.mp4"
        t0 = time.time()
        for frac in (0.25, 0.5, 1.0):
            n = int(total * frac)
            on_event({"type": "progress", "stage": "render", "renderedFrames": n, "encodedFrames": n,
                      "totalFrames": total, "elapsedMs": int((time.time() - t0) * 1000)})  # fmt: skip
        # A tiny 64x? clip keeps tests fast; the size check uses the preset (scaled by ffmpeg here).
        subprocess.run(
            [str(self.ffmpeg), "-hide_banner", "-v", "error", "-y",
             "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate={fps}",
             "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
             "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "40", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-shortest", str(mp4)],
            check=True, capture_output=True,
        )  # fmt: skip
        srt = out_dir / "video.srt"
        vtt = out_dir / "video.vtt"
        t = 0.0
        cues = []
        for i, s in enumerate(spec.scenes):
            cues.append((i + 1, t + 0.3, t + s.duration_s - 0.5, s.narration.replace("*", "")))
            t += s.duration_s
        srt.write_text(
            "\n".join(f"{n}\n{_stamp(a, ',')} --> {_stamp(b, ',')}\n{txt}\n" for n, a, b, txt in cues),
            "utf-8",
        )
        vtt.write_text(
            "WEBVTT\n\n"
            + "\n".join(f"{_stamp(a, '.')} --> {_stamp(b, '.')}\n{txt}\n" for _, a, b, txt in cues),
            "utf-8",
        )
        quiz = out_dir / "quiz.json"
        qs = [s.model_dump() for s in spec.scenes if s.template == "quiz_question"]
        quiz.write_text(
            json.dumps({"title": spec.title, "lang": spec.lang, "questions": qs}, ensure_ascii=False), "utf-8"
        )
        ms = int((time.time() - t0) * 1000) or 1
        return {
            "type": "done", "mp4": str(mp4), "srt": str(srt), "vtt": str(vtt), "quiz": str(quiz),
            "durationMs": ms, "totalFrames": total,
            "stages": {"validate_ms": 1, "bundle_ms": 1, "render_ms": ms, "encode_ms": 0, "post_ms": 0},
            "checks": [], "cacheHits": {"bundle": True},
        }  # fmt: skip
