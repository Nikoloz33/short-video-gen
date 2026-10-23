"""Deterministic gates that OVERRIDE the LLM verdict, plus translation gates."""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent.factcheck.normalize import is_negated, missing_names, missing_quantities, quantities


@dataclass(frozen=True)
class GateResult:
    ok: bool
    gate: str | None = None
    why: str | None = None


def closest_clause(claim: str, quote: str) -> str:
    """The clause of `quote` the claim paraphrases. Quotes often join an instruction and a
    prohibition ("use the hand-wash sink only — never use a food sink"); polarity must be compared
    with the matching clause, not the whole quote."""
    from rapidfuzz import fuzz

    clauses = [c.strip() for c in re.split(r"[;—–]|\. |, but |\bbut\b|: ", quote) if c.strip()]
    if len(clauses) <= 1:
        return quote
    return max(clauses, key=lambda c: fuzz.token_set_ratio(claim.lower(), c.lower()))


def check_claim(claim: str, evidence: str, quote: str | None) -> GateResult:
    """Numbers/units must occur in the evidence, names must appear, polarity must match the quote."""
    miss_q = missing_quantities(claim, evidence)
    if miss_q:
        return GateResult(False, "numbers", f"not in the source: {', '.join(map(str, miss_q))}")
    miss_n = missing_names(claim, evidence)
    if miss_n:
        return GateResult(False, "names", f"not in the source: {', '.join(miss_n)}")
    if quote and is_negated(claim) != is_negated(closest_clause(claim, quote)):
        return GateResult(
            False,
            "polarity",
            "the claim says the opposite of the source"
            if is_negated(claim)
            else "the source states this as a prohibition",
        )
    return GateResult(True)


def check_translation(source: str, translated: str, back_translated: str) -> list[str]:
    """Problems with a translation: numbers that changed (both directions), lost names, flipped
    negation (checked on the back-translation, which is in the source language)."""
    problems: list[str] = []
    # A bare 0/1 ("Step 1", "one quiz") is often spelled out or dropped in translation: ignore it.
    src_q = sorted((q.value, q.unit or "") for q in quantities(source) if q.unit or q.value not in (0.0, 1.0))
    tr_q = sorted(
        (q.value, q.unit or "") for q in quantities(translated) if q.unit or q.value not in (0.0, 1.0)
    )
    if [v for v, _ in src_q] != [v for v, _ in tr_q]:
        problems.append(f"numbers differ: source {src_q} vs translation {tr_q}")
    # Names of the source must survive (one direction: compounds like "handwashing" translate into
    # separate words, so extra glossary hits in the translation are not errors).
    miss = missing_names(source, translated)
    if miss:
        problems.append(f"names lost in translation: {', '.join(sorted(set(miss)))}")
    if is_negated(source) != is_negated(back_translated):
        problems.append("negation flipped in translation")
    return problems
