"""Deterministic validation of a rendered video (ffprobe + files + spec facts)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from agent.config import load_app
from agent.schemas.video_spec import VideoSpec

SIZES = {"preview": (540, 960, 15), "final": (1080, 1920, 30)}


def ffprobe(ffprobe_bin: Path, mp4: Path) -> dict[str, Any]:
    r = subprocess.run(
        [str(ffprobe_bin), "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,width,height,r_frame_rate:format=duration,size", "-of", "json", str(mp4)],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    j = json.loads(r.stdout)
    v: dict[str, Any] = next((s for s in j["streams"] if s["codec_type"] == "video"), {})
    a: dict[str, Any] = next((s for s in j["streams"] if s["codec_type"] == "audio"), {})
    num, den = (v.get("r_frame_rate") or "0/1").split("/")
    return {
        "width": v.get("width", 0),
        "height": v.get("height", 0),
        "fps": float(num) / float(den or 1),
        "duration": float(j["format"]["duration"]),
        "vcodec": v.get("codec_name", "none"),
        "acodec": a.get("codec_name", "none"),
        "size": int(j["format"].get("size", 0)),
    }


def validate_video(
    spec: VideoSpec, preset: str, result: dict[str, Any], ffprobe_bin: Path, strict_duration: bool = True
) -> list[dict[str, Any]]:
    app = load_app()
    mp4 = Path(result["mp4"])
    info = ffprobe(ffprobe_bin, mp4)
    w, h, fps = SIZES[preset]
    planned = spec.total_s
    checks: list[dict[str, Any]] = [
        {"name": "codecs", "ok": info["vcodec"] == "h264" and info["acodec"] == "aac",
         "detail": f"{info['vcodec']}/{info['acodec']}"},
        {"name": "resolution", "ok": (info["width"], info["height"]) == (w, h), "detail": f"{info['width']}x{info['height']}"},
        {"name": "fps", "ok": abs(info["fps"] - fps) < 0.01, "detail": f"{info['fps']:g}"},
        {"name": "length", "ok": abs(info["duration"] - planned) <= 0.3,
         "detail": f"{info['duration']:.2f} s (planned {planned:.2f} s)"},
    ]  # fmt: skip
    if strict_duration:
        lo, hi = app.min_duration_s, app.max_duration_s
        checks.append({"name": "duration_range", "ok": lo <= info["duration"] <= min(hi, app.hard_cap_s),
                       "detail": f"{info['duration']:.1f} s (allowed {lo:g}-{hi:g} s)"})  # fmt: skip
    srt = Path(result.get("srt", ""))
    checks.append({"name": "captions", "ok": srt.is_file() and srt.stat().st_size > 0, "detail": srt.name})
    missing_audio = [s.id for s in spec.scenes if s.audio is None]
    checks.append({"name": "narration", "ok": not missing_audio,
                   "detail": "all scenes narrated" if not missing_audio else f"no audio: {', '.join(missing_audio)}"})  # fmt: skip
    overrun = [
        s.id for s in spec.scenes if s.audio and s.audio.start_s + s.audio.duration_s > s.duration_s + 1e-6
    ]
    checks.append(
        {"name": "clips_fit", "ok": not overrun, "detail": ", ".join(overrun) or "every clip fits its scene"}
    )
    return checks
