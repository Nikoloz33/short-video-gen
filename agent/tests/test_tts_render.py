from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from agent.llm.fake import pcm_tone, silent_wav
from agent.llm.router import LLMRouter
from agent.llm.types import RetryableError
from agent.render.validate import validate_video
from agent.render.worker import FakeRenderer, RenderError, RenderWorker
from agent.schemas.video_spec import AudioClip, VideoSpec
from agent.settings import REPO_ROOT, Settings
from agent.translate import translate_spec
from agent.tts.narrator import NarrationError, Narrator, cache_key, transcript_matches
from agent.tts.wav import pcm_rate, pcm_to_wav, to_wav, wav_duration

SPEC = VideoSpec.model_validate_json((REPO_ROOT / "data/fixtures/specs/handwash-en.json").read_text("utf-8"))


def test_pcm_wav_helpers() -> None:
    pcm = pcm_tone(0.5)
    wav = pcm_to_wav(pcm, 24000)
    assert wav[:4] == b"RIFF" and wav_duration(wav) == pytest.approx(0.5)
    assert to_wav(pcm, "audio/L16;rate=16000")[:4] == b"RIFF"
    assert wav_duration(to_wav(pcm, "audio/L16;rate=16000")) == pytest.approx(0.75)
    assert to_wav(wav, "audio/wav") is wav
    assert pcm_rate("audio/L16") == 24000
    with pytest.raises(ValueError, match="unsupported"):
        to_wav(b"xx", "audio/mp3")


def test_cache_key_changes_with_prompt_version() -> None:
    a = cache_key("m", "Kore", "ka", "text")
    assert a == cache_key("m", "Kore", "ka", "text")
    assert a != cache_key("m", "Kore", "ka", "text", version=2)
    assert a != cache_key("m", "Puck", "ka", "text")


def test_transcript_gate() -> None:
    ok, sim, _ = transcript_matches("Wash your hands for 20 seconds.", "wash your hands for 20 seconds")
    assert ok and sim > 0.95
    bad, _, why = transcript_matches("Wash your hands for 20 seconds.", "Wash your hands for 2 seconds.")
    assert not bad and "numbers" in why
    bad, _, why = transcript_matches("Wash your hands.", "Read calmly: wash your hands, and dance now.")
    assert not bad and "similarity" in why


def _narrator(router: LLMRouter, tmp_path: Path, transcripts: list[str]) -> Narrator:
    fake: Any = router.backend
    fake.responses["transcribe"] = list(transcripts)
    return Narrator(router, tmp_path / "tts", Path("does-not-exist-ffmpeg"), verify=True)


def test_narrator_caches_and_verifies(router: LLMRouter, tmp_path: Path) -> None:
    n = _narrator(router, tmp_path, ["Wash your hands for 20 seconds."])
    clip, usage = n.synth("Wash your hands for 20 seconds.", "en", "Kore")
    assert not clip.cache_hit and clip.duration_s > 0.4 and usage.by_role("tts") is not None
    again, usage2 = n.synth("Wash your hands for 20 seconds.", "en", "Kore")
    assert again.cache_hit and usage2.cost_usd == 0


def test_narrator_retries_then_fails(router: LLMRouter, tmp_path: Path) -> None:
    n = _narrator(router, tmp_path, ["something else entirely", "Wash."])
    clip, _ = n.synth("Wash.", "en", "Kore")
    assert not clip.cache_hit  # second attempt passed
    n2 = _narrator(router, tmp_path / "b", ["nope", "still nope"])
    with pytest.raises(NarrationError, match="twice"):
        n2.synth("Rinse under running water.", "en", "Kore")


def test_tts_429_then_success(router: LLMRouter, tmp_path: Path) -> None:
    fake: Any = router.backend
    fake.tts_failures = [RetryableError("quota", 429), RetryableError("quota", 429)]
    n = Narrator(router, tmp_path / "tts", Path("x"), verify=False)
    clip, _ = n.synth("Dry your hands.", "en", "Kore")
    assert clip.duration_s > 0


def test_translate_spec_with_gates(router: LLMRouter) -> None:
    fake: Any = router.backend
    out, problems, usage = translate_spec(SPEC, "ka", router)  # identity fake translation
    assert out.lang == "ka" and all(s.audio is None for s in out.scenes)
    assert problems == {} and usage.by_role("translate") and usage.by_role("back_translation")
    same, p2, _ = translate_spec(out, "ka", router)
    assert same is out and p2 == {}

    def broken(req: Any) -> dict[str, Any]:
        return {
            "title": "T",
            "scenes": [{"scene_id": "s5", "narration": "Scrub for 2 seconds.", "texts": ["x"]}],
        }

    fake.responses["translate"] = broken
    fake.responses["back_translation"] = broken
    _, problems, _ = translate_spec(SPEC, "ka", router)
    assert "s1" in problems and "translation missing" in problems["s1"][0]
    assert any("numbers" in p for p in problems["s5"])


def test_fake_renderer_and_validation(settings: Settings, tmp_path: Path) -> None:
    spec = SPEC.model_copy(
        update={
            "scenes": [
                s.model_copy(update={"audio": AudioClip(src="a.wav", duration_s=1.0, start_s=0.3)})
                for s in SPEC.scenes
            ]
        }
    )
    r = FakeRenderer(settings.ffmpeg())
    events: list[dict[str, Any]] = []
    res = r.render(spec, "preview", tmp_path / "out", tmp_path, events.append)
    assert events[-1]["renderedFrames"] == events[-1]["totalFrames"]
    checks = validate_video(spec, "preview", res, settings.ffmpeg("ffprobe"))
    assert all(c["ok"] for c in checks), checks
    assert json.loads(Path(res["quiz"]).read_text("utf-8"))["questions"]
    bad = validate_video(SPEC, "final", res, settings.ffmpeg("ffprobe"))
    failed = {c["name"] for c in bad if not c["ok"]}
    assert {"resolution", "fps", "narration"} <= failed
    assert r.check(spec) == []


def _subdir(root: Path, name: str) -> Path:
    (root / name).mkdir()
    return root / name


def _worker_with_script(tmp_path: Path, js: str) -> RenderWorker:
    w = RenderWorker(tmp_path)
    w.cli = tmp_path / "noop.mjs"
    w.cli.write_text("", "utf-8")
    w.script = tmp_path / "w.mjs"
    w.script.write_text(js, "utf-8")
    # node <cli> <script>: make the "cli" just import the script.
    w.cli.write_text(f"await import({json.dumps(w.script.as_uri())});", "utf-8")
    return w


@pytest.mark.skipif(
    sys.platform == "win32" and not Path("C:/Program Files/nodejs/node.exe").exists(), reason="node"
)
def test_worker_protocol_with_fake_node_script(tmp_path: Path) -> None:
    ok = _worker_with_script(
        tmp_path,
        "let s='';process.stdin.on('data',d=>s+=d);process.stdin.on('end',()=>{const r=JSON.parse(s);"
        "console.log('noise');"
        "console.log(JSON.stringify({type:'progress',stage:'render',renderedFrames:1,totalFrames:2}));"
        "console.log(JSON.stringify(r.cmd==='check'?{type:'check',ok:false,issues:[{code:'x'}]}:{type:'done',mp4:'v.mp4'}));});",
    )
    seen: list[dict[str, Any]] = []
    assert ok.render(SPEC, "preview", tmp_path, tmp_path, seen.append)["mp4"] == "v.mp4"
    assert seen[0]["stage"] == "render"
    assert ok.check(SPEC, {"minTotalS": 1}) == [{"code": "x"}]

    err = _worker_with_script(
        _subdir(tmp_path, "e"),
        "process.stdin.resume();process.stdin.on('end',()=>{console.log(JSON.stringify({type:'error',code:'invalid_spec',message:'bad'}));process.exit(2)});",
    )
    assert err.check(SPEC)[0]["code"] == "invalid_spec"
    with pytest.raises(RenderError, match="invalid_spec"):
        err.render(SPEC, "final", tmp_path, tmp_path, lambda _e: None)
    crash = _worker_with_script(_subdir(tmp_path, "c"),
                                "process.stdin.resume();process.stdin.on('end',()=>process.exit(1));")  # fmt: skip
    with pytest.raises(RenderError, match="worker_crashed"):
        crash.render(SPEC, "final", tmp_path, tmp_path, lambda _e: None)
    assert silent_wav(0.1)[:4] == b"RIFF"
