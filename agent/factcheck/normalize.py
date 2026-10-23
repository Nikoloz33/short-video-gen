"""Language-independent extraction of quantities (number + unit), polarity and names (en / ka)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache

from agent.settings import get_settings

# ---- numbers -----------------------------------------------------------------------------------

_EN_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
    "thousand": 1000, "half": 0.5, "once": 1, "twice": 2, "thrice": 3, "single": 1, "double": 2,
}  # fmt: skip
_EN_TIMES_WORDS = {"once": 1, "twice": 2, "thrice": 3}

# Georgian number stems (case endings are stripped before lookup).
_KA_STEMS = {
    "ნულ": 0, "ერთ": 1, "ორ": 2, "სამ": 3, "ოთხ": 4, "ხუთ": 5, "ექვს": 6, "შვიდ": 7, "რვ": 8,
    "ცხრ": 9, "ათ": 10, "თერთმეტ": 11, "თორმეტ": 12, "ცამეტ": 13, "თოთხმეტ": 14, "თხუთმეტ": 15,
    "თექვსმეტ": 16, "ჩვიდმეტ": 17, "თვრამეტ": 18, "ცხრამეტ": 19, "ოც": 20, "ოცდაათ": 30,
    "ორმოც": 40, "ორმოცდაათ": 50, "სამოც": 60, "სამოცდაათ": 70, "ოთხმოც": 80, "ოთხმოცდაათ": 90,
    "ას": 100, "ათას": 1000, "ნახევარ": 0.5,
}  # fmt: skip
_KA_ENDINGS = ("ისთვის", "იდან", "ამდე", "ჯერ", "ით", "ის", "ად", "ში", "ზე", "ს", "ი", "ა", "")

# ---- units -------------------------------------------------------------------------------------

_UNITS: list[tuple[str, tuple[str, ...]]] = [
    ("mg", ("mg", "milligram", "milligrams", "მგ", "მილიგრამი", "მილიგრამ")),
    ("mcg", ("mcg", "µg", "microgram", "micrograms", "მკგ")),
    ("g", ("g", "gram", "grams", "გ", "გრამი", "გრამ")),
    ("ml", ("ml", "millilitre", "milliliter", "millilitres", "milliliters", "მლ", "მილილიტრი")),
    ("l", ("l", "litre", "liter", "litres", "liters", "ლ", "ლიტრი")),
    ("s", ("s", "sec", "secs", "second", "seconds", "წმ", "წამი", "წამ", "წამის", "წამით", "წამს")),
    ("min", ("min", "mins", "minute", "minutes", "წთ", "წუთი", "წუთ", "წუთის", "წუთით", "წუთს")),
    ("h", ("h", "hr", "hrs", "hour", "hours", "სთ", "საათი", "საათ", "საათის", "საათში", "საათით", "საათს")),
    ("day", ("day", "days", "daily", "დღე", "დღის", "დღეში", "დღით", "დღეს", "დღეები")),
    ("week", ("week", "weeks", "weekly", "კვირა", "კვირის", "კვირაში", "კვირით")),
    ("month", ("month", "months", "თვე", "თვის", "თვეში")),
    ("c", ("°c", "°", "degrees", "degree", "celsius", "გრადუსი", "გრადუს", "°ც")),
    ("percent", ("%", "percent", "პროცენტი")),
    ("times", ("times", "time", "x", "ჯერ", "ჯერზე")),
    (
        "tablet",
        ("tablet", "tablets", "pill", "pills", "capsule", "capsules", "ტაბლეტი", "ტაბლეტ", "აბი", "კაფსულა"),
    ),
    ("drop", ("drop", "drops", "წვეთი", "წვეთ")),
    ("cm", ("cm", "centimetre", "centimeter", "სმ", "სანტიმეტრი")),
    ("m", ("m", "metre", "meter", "metres", "meters", "მ", "მეტრი")),
    ("kg", ("kg", "kilogram", "kilograms", "კგ", "კილოგრამი")),
]
_UNIT_OF = {syn: canon for canon, syns in _UNITS for syn in syns}


@dataclass(frozen=True)
class Quantity:
    value: float
    unit: str | None

    def __str__(self) -> str:
        v = int(self.value) if self.value == int(self.value) else self.value
        return f"{v} {self.unit}" if self.unit else str(v)


_TOKEN = re.compile(r"\d+(?:[.,]\d+)?|[^\W\d_]+|%|°\w?", re.UNICODE)
_CLOCK = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")


def _ka_number(word: str) -> tuple[float, bool] | None:
    """(value, is_times) for a Georgian number word such as ოცი / ოც / სამჯერ / რვა."""
    times = word.endswith("ჯერ")
    base = word[: -len("ჯერ")] if times else word
    for end in _KA_ENDINGS:
        if end and not base.endswith(end):
            continue
        stem = base[: len(base) - len(end)] if end else base
        if stem in _KA_STEMS:
            return float(_KA_STEMS[stem]), times
    return None


def _number(tok: str) -> tuple[float, bool] | None:
    if tok[0].isdigit():
        return float(tok.replace(",", ".")), False
    low = tok.lower()
    if low in _EN_WORDS:
        return float(_EN_WORDS[low]), low in _EN_TIMES_WORDS
    if "ა" <= tok[0] <= "ჿ":
        return _ka_number(tok)
    return None


def quantities(text: str) -> list[Quantity]:
    """Numbers with the unit that follows them (or a 'times' marker). Clock times become minutes
    since midnight with unit 'clock'. Compound English numbers ('twenty five') are summed."""
    out: list[Quantity] = []
    for m in _CLOCK.finditer(text):
        out.append(Quantity(int(m.group(1)) * 60 + int(m.group(2)), "clock"))
    text = _CLOCK.sub(" ", text)
    toks = _TOKEN.findall(text)
    i = 0
    while i < len(toks):
        n = _number(toks[i])
        if n is None:
            i += 1
            continue
        value, times = n
        j = i + 1
        # twenty five / ოცდახუთი handled as one word; "twenty five" summed here
        while (
            j < len(toks)
            and (nn := _number(toks[j])) is not None
            and not nn[1]
            and value >= 20
            and nn[0] < 10
        ):
            value += nn[0]
            j += 1
        unit: str | None = "times" if times else None
        if unit is None and j < len(toks):
            unit = _UNIT_OF.get(toks[j].lower())
            if unit is None and j + 1 < len(toks) and toks[j].lower() in {"a", "an", "per"}:
                unit = _UNIT_OF.get(toks[j + 1].lower())
            if unit is not None:
                j += 1
        if unit is None and j < len(toks) and toks[j].lower().startswith("ჯერ"):
            unit, j = "times", j + 1
        out.append(Quantity(value, unit))
        i = j
    return out


def missing_quantities(claim: str, evidence: str) -> list[Quantity]:
    """Quantities in `claim` with no match in `evidence` (same value; same unit when both have one).
    Bare 1 without a unit is ignored ("one tablet" vs "a tablet", "step one")."""
    ev = quantities(evidence)
    missing: list[Quantity] = []
    for q in quantities(claim):
        if q.unit is None and q.value in (1.0, 0.0):
            continue
        ok = any(e.value == q.value and (e.unit == q.unit or e.unit is None or q.unit is None) for e in ev)
        if not ok:
            missing.append(q)
    return missing


# ---- polarity ----------------------------------------------------------------------------------

_NEG = re.compile(
    r"\b(not|never|no|don't|do not|doesn't|cannot|can't|mustn't|must not|avoid|without|stop|prohibited|forbidden)\b"
    r"|(?<![ა-ჿ])(არ|ნუ|არასოდეს|აკრძალულია|მოერიდეთ|გარეშე)(?![ა-ჿ])",
    re.IGNORECASE,
)


def is_negated(text: str) -> bool:
    return _NEG.search(text) is not None


# ---- names (glossary + drug-like words) --------------------------------------------------------


@lru_cache(maxsize=1)
def glossary() -> list[dict[str, list[str] | str]]:
    path = get_settings().data_dir / "glossary" / "medical.json"
    terms: list[dict[str, list[str] | str]] = json.loads(path.read_text("utf-8"))["terms"]
    return terms


_DRUG = re.compile(
    r"\b[A-Za-z]{4,}(?:cillin|mycin|cycline|azole|prazole|pril|sartan|olol|statin|mab|profen|amol|formin|parin|oxacin)\b",
    re.I,
)


def _contains(text: str, form: str) -> bool:
    if "ა" <= form[:1] <= "ჿ":
        return form in text
    return re.search(rf"\b{re.escape(form)}\b", text, re.IGNORECASE) is not None


def missing_names(claim: str, evidence: str) -> list[str]:
    """Glossary terms / drug-like words in the claim whose forms (any language) are absent from the
    evidence. Unknown drug names are fuzzy-matched against evidence words."""
    from rapidfuzz import fuzz

    missing: list[str] = []
    for term in glossary():
        forms = [*term["en"], *term["ka"]]
        if any(_contains(claim, f) for f in forms) and not any(_contains(evidence, f) for f in forms):
            missing.append(str(term["en"][0]))
    known = {f.lower() for t in glossary() for f in [*t["en"], *t["ka"]]}
    ev_words = set(re.findall(r"\w+", evidence.lower()))
    for m in _DRUG.finditer(claim):
        w = m.group(0).lower()
        if w in known:
            continue
        if not any(fuzz.ratio(w, e) >= 85 for e in ev_words):
            missing.append(m.group(0))
    return missing
