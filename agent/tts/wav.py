"""WAV helpers: wrap raw L16 PCM (Gemini TTS) into WAV, read durations."""

from __future__ import annotations

import io
import re
import wave
from pathlib import Path


def pcm_rate(mime_type: str, default: int = 24000) -> int:
    m = re.search(r"rate=(\d+)", mime_type)
    return int(m.group(1)) if m else default


def pcm_to_wav(pcm: bytes, rate: int = 24000, channels: int = 1, sampwidth: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def to_wav(data: bytes, mime_type: str) -> bytes:
    """Gemini returns either a WAV file or raw `audio/L16;rate=24000` PCM."""
    if data[:4] == b"RIFF":
        return data
    if "l16" in mime_type.lower() or "pcm" in mime_type.lower():
        return pcm_to_wav(data, pcm_rate(mime_type))
    raise ValueError(f"unsupported TTS audio format {mime_type!r}")


def wav_duration(source: bytes | Path) -> float:
    f = io.BytesIO(source) if isinstance(source, bytes) else source.open("rb")
    with f, wave.open(f, "rb") as w:
        return w.getnframes() / float(w.getframerate())
