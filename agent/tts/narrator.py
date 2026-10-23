"""Synthesise one narration clip per scene.

Rules (learned the hard way):
- send ONLY the narration text (style prefixes get read aloud; system_instruction is a 400);
- cache by sha256(model|voice|language|text|TTS_PROMPT_VERSION) — bump the version whenever the
  request format changes, or stale audio comes back from the cache;
- loudness-normalise each clip (loudnorm I=-16 TP=-1.5, mono 24 kHz);
- transcribe every new clip (Flash) and compare: normalised similarity >= 0.85 and every number
  present; retry once, then fail the scene with a clear message.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from rapidfuzz import fuzz

from agent.config import Language, load_app
from agent.factcheck.normalize import missing_quantities
from agent.llm.router import LLMRouter
from agent.llm.types import Attachment
from agent.llm.usage import Usage, merge_usage
from agent.prompts import load_prompt
from agent.tts.wav import to_wav, wav_duration

TTS_PROMPT_VERSION = 1
MIN_SIMILARITY = 0.85
LANG_NAME = {"ka": "Georgian", "en": "English"}


class NarrationError(RuntimeError):
    pass


@dataclass
class Clip:
    path: Path
    duration_s: float
    cache_hit: bool
    similarity: float
    transcript: str


def cache_key(model: str, voice: str, lang: str, text: str, version: int = TTS_PROMPT_VERSION) -> str:
    return hashlib.sha256(f"{model}|{voice}|{lang}|{text}|v{version}".encode()).hexdigest()


def normalize_for_compare(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower().replace("*", "")
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def transcript_matches(narration: str, transcript: str) -> tuple[bool, float, str]:
    sim = fuzz.ratio(normalize_for_compare(narration), normalize_for_compare(transcript)) / 100.0
    missing = missing_quantities(narration, transcript)
    if missing:
        return False, sim, f"numbers missing from the audio: {', '.join(map(str, missing))}"
    if sim < MIN_SIMILARITY:
        return False, sim, f"audio does not match the narration (similarity {sim:.2f})"
    return True, sim, ""


class Narrator:
    def __init__(self, router: LLMRouter, cache_dir: Path, ffmpeg: Path, *, verify: bool = True) -> None:
        self.router = router
        self.cache_dir = cache_dir
        self.ffmpeg = ffmpeg
        self.verify = verify
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _normalize(self, raw_wav: bytes, out: Path) -> None:
        tmp = out.with_suffix(".raw.wav")
        tmp.write_bytes(raw_wav)
        try:
            subprocess.run(
                [str(self.ffmpeg), "-hide_banner", "-v", "error", "-y", "-i", str(tmp),
                 "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ac", "1", "-ar", "24000", str(out)],
                check=True, capture_output=True,
            )  # fmt: skip
        except (subprocess.CalledProcessError, FileNotFoundError):
            out.write_bytes(raw_wav)  # keep the clip; loudness is re-checked on the final mix
        finally:
            tmp.unlink(missing_ok=True)

    def _transcribe(self, wav: bytes, lang: Language) -> tuple[str, Usage]:
        r = self.router.text(
            "transcribe",
            load_prompt("transcribe").render(lang_name=LANG_NAME[lang]),
            attachments=[Attachment(wav, "audio/wav")],
        )
        return r.text.strip(), r.usage

    def synth(self, text: str, lang: Language, voice: str) -> tuple[Clip, Usage]:
        model = self.router.models.role("tts").model
        key = cache_key(model, voice, lang, text)
        path = self.cache_dir / f"{key}.wav"
        meta = path.with_suffix(".json")
        if path.exists() and meta.exists():
            m = json.loads(meta.read_text("utf-8"))
            return Clip(path, wav_duration(path), True, m["similarity"], m["transcript"]), Usage()

        code = load_app().languages[lang].tts_code
        usage = Usage()
        last_problem = ""
        for _attempt in range(2):
            r = self.router.tts(text, code, voice)
            usage = merge_usage(usage, r.usage)
            self._normalize(to_wav(r.data, r.mime_type), path)
            transcript, sim = "", 1.0
            if self.verify:
                transcript, u = self._transcribe(path.read_bytes(), lang)
                usage = merge_usage(usage, u)
                ok, sim, last_problem = transcript_matches(text, transcript)
                if not ok:
                    continue
            meta.write_text(json.dumps({"similarity": sim, "transcript": transcript, "text": text}), "utf-8")
            return Clip(path, wav_duration(path), False, sim, transcript), usage
        path.unlink(missing_ok=True)
        raise NarrationError(f"TTS failed the transcript check twice: {last_problem}")


def clip_record(clip: Clip) -> dict[str, object]:
    d = asdict(clip)
    d["path"] = str(clip.path)
    return d
