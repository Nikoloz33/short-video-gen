"""Uploaded text is DATA. Normalise it and drop lines that try to instruct the model."""

from __future__ import annotations

import re
import unicodedata

_INJECTION = re.compile(
    r"(ignore|disregard|forget)\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instructions|prompts?)"
    r"|you\s+are\s+(now\s+)?(an?\s+)?(ai|assistant|language model|chatgpt|gemini|claude)"
    r"|\b(system|developer)\s*(prompt|message)\s*:"
    r"|^\s*(assistant|system)\s*:"
    r"|\bact\s+as\b.{0,40}\b(assistant|model|ai)\b"
    r"|do\s+not\s+follow\s+(the|your)\s+(rules|instructions)"
    r"|წინა\s+ინსტრუქციები"
    r"|უგულებელყავი",
    re.IGNORECASE | re.MULTILINE,
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"-\n(?=[a-z])", "", text)  # de-hyphenate PDF line breaks
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_injections(text: str) -> tuple[str, list[str]]:
    """Returns (clean text, removed lines)."""
    kept: list[str] = []
    removed: list[str] = []
    for line in text.split("\n"):
        (removed if _INJECTION.search(line) else kept).append(line)
    return "\n".join(kept), [r.strip() for r in removed if r.strip()]
