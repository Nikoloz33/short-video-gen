"""Listening check: render sample sentences per language and voice into out/tts-check/ for a human
to listen to BEFORE changing the default voice or TTS model. Also prints the transcript similarity.

    uv run python scripts/check_tts.py [--voices Kore,Puck] [--langs ka,en]
"""

from __future__ import annotations

import argparse
import shutil
import sys

from agent.llm.factory import build_router
from agent.logging import configure
from agent.settings import REPO_ROOT, get_settings
from agent.tts.narrator import Narrator

SAMPLES = {
    "en": [
        "Wash your hands with soap for at least 20 seconds.",
        "Take 500 mg every 8 hours. Do not take more than 4 doses in 24 hours.",
    ],
    "ka": [
        "დაიბანეთ ხელები საპნით მინიმუმ 20 წამის განმავლობაში.",
        "მიიღეთ 500 მგ ყოველ 8 საათში. არ მიიღოთ 4 დოზაზე მეტი 24 საათში.",
    ],
}


def main() -> int:
    configure(level="WARNING")
    p = argparse.ArgumentParser()
    p.add_argument("--voices", default="Kore")
    p.add_argument("--langs", default="ka,en")
    args = p.parse_args()
    settings = get_settings()
    narrator = Narrator(build_router(settings), settings.data_dir / "cache" / "tts", settings.ffmpeg())
    out = REPO_ROOT / "out" / "tts-check"
    out.mkdir(parents=True, exist_ok=True)
    for voice in args.voices.split(","):
        for lang in args.langs.split(","):
            for i, text in enumerate(SAMPLES[lang]):
                clip, _ = narrator.synth(text, lang, voice)  # type: ignore[arg-type]
                dst = out / f"{voice}-{lang}-{i + 1}.wav"
                shutil.copyfile(clip.path, dst)
                sys.stdout.write(f"{dst.name}: {clip.duration_s:.2f} s, similarity {clip.similarity:.2f}\n")
    sys.stdout.write(f"Listen to the files in {out} before changing the default voice.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
