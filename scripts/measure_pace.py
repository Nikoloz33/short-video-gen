"""Measure the TTS speaking pace (characters per second) per language, to set `chars_per_sec` in
config/app.yaml. The script writer's character budget comes from these numbers; real timing always
comes from measured clip durations.

    uv run python scripts/measure_pace.py [--voice Kore]
"""

from __future__ import annotations

import argparse
import sys

from agent.llm.factory import build_router
from agent.logging import configure
from agent.settings import get_settings
from agent.tts.narrator import Narrator

TEXTS = {
    "en": [
        "Wet your hands with warm running water and apply liquid soap from the dispenser.",
        "Keep the dressing clean and dry for 48 hours, then you may shower.",
        "Never touch ready-to-eat food with bare hands; use clean gloves or utensils.",
    ],
    "ka": [
        "დაისველეთ ხელები თბილი გამდინარე წყლით და დაიტანეთ თხევადი საპონი.",
        "სახვევი შეინახეთ სუფთა და მშრალი 48 საათის განმავლობაში, შემდეგ შეგიძლიათ შხაპის მიღება.",
        "არასოდეს შეეხოთ მზა საკვებს შიშველი ხელებით; გამოიყენეთ სუფთა ხელთათმანები.",
    ],
}


def main() -> int:
    configure(level="WARNING")
    p = argparse.ArgumentParser()
    p.add_argument("--voice", default="Kore")
    args = p.parse_args()
    settings = get_settings()
    narrator = Narrator(build_router(settings), settings.data_dir / "cache" / "tts", settings.ffmpeg())
    for lang, texts in TEXTS.items():
        chars = secs = 0.0
        for t in texts:
            clip, _ = narrator.synth(t, lang, args.voice)  # type: ignore[arg-type]
            chars += len(t)
            secs += clip.duration_s
        sys.stdout.write(f"{lang}: {chars / secs:.2f} chars/s over {secs:.1f} s of audio\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
