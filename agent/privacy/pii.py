"""PII scrubber. Runs on every upload BEFORE anything leaves the machine:
1. deterministic patterns (emails, phones, dates of birth, ID / MRN numbers, labelled names, addresses);
2. optionally a Flash pass over the ALREADY regex-redacted text for names the patterns missed.
The user sees what was redacted (kind + a masked preview), never the raw values in logs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent.llm.router import LLMRouter
from agent.llm.usage import Usage
from agent.prompts import load_prompt, source_block
from agent.schemas.llm_io import PiiFindings


@dataclass(frozen=True)
class Redaction:
    kind: str
    preview: str  # masked, e.g. "J*** S****"


_LABEL = r"(?:patient|name|full name|pt|პაციენტი|სახელი|გვარი|სახელი და გვარი)"
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    (
        "mrn",
        re.compile(r"\b(?:MRN|medical record(?: number)?|სამედიცინო ბარათი)\s*[:#№]?\s*[A-Z0-9-]{4,}", re.I),
    ),
    ("id", re.compile(r"\b(?:ID|personal (?:no|number)|პირადი ნომერი|პ/ნ)\s*[:#№]?\s*\d{6,}", re.I)),
    ("id", re.compile(r"\b\d{11}\b")),  # Georgian personal number
    (
        "dob",
        re.compile(
            r"\b(?:DOB|date of birth|born|დაბადების თარიღი)\s*[:]?\s*\d{1,4}[./-]\d{1,2}[./-]\d{1,4}", re.I
        ),
    ),
    (
        "phone",
        re.compile(r"(?<!\w)(?:\+?\d{3}[\s-]?)?\(?\d{3}\)?[\s-]?\d{2,3}[\s-]?\d{2,3}[\s-]?\d{0,3}(?!\w)"),
    ),
    ("name", re.compile(rf"\b{_LABEL}\s*[:]\s*([^\n,;]{{2,60}})", re.I)),
    ("address", re.compile(r"\b(?:address|მისამართი)\s*[:]\s*[^\n]{4,80}", re.I)),
]


def _mask(value: str) -> str:
    return " ".join(w[:1] + "*" * max(0, len(w) - 1) for w in value.split())[:40]


def regex_scrub(text: str) -> tuple[str, list[Redaction]]:
    found: list[Redaction] = []
    for kind, pat in _PATTERNS:

        def repl(m: re.Match[str], kind: str = kind) -> str:
            value = m.group(0)
            if kind == "phone" and sum(ch.isdigit() for ch in value) < 9:
                return value  # doses, times and step numbers are not phone numbers
            found.append(Redaction(kind, _mask(value)))
            return f"[REDACTED:{kind}]"

        text = pat.sub(repl, text)
    return text, found


def scrub(text: str, router: LLMRouter | None = None) -> tuple[str, list[Redaction], Usage]:
    clean, found = regex_scrub(text)
    usage = Usage()
    if router is not None and clean.strip():
        prompt = load_prompt("pii_scrub").render(document=source_block(clean[:30000]))
        r = router.structured("pii_scrub", prompt, PiiFindings)
        usage = r.usage
        for span in r.value.spans:
            if span.text and span.text in clean and "[REDACTED" not in span.text and len(span.text) > 2:
                clean = clean.replace(span.text, f"[REDACTED:{span.kind}]")
                found.append(Redaction(span.kind, _mask(span.text)))
    return clean, found, usage
