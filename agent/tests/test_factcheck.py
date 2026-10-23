from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent.evals.run import gates_only, run_offline, summarize, write_report
from agent.factcheck.checker import FactReport, SceneReport, check_scene
from agent.factcheck.gates import check_claim, check_translation, closest_clause
from agent.factcheck.normalize import Quantity, is_negated, missing_names, missing_quantities, quantities
from agent.llm.router import LLMRouter
from agent.llm.types import GenRequest
from agent.rag.chunking import chunk_pages
from agent.rag.embeddings import Embedder
from agent.rag.loaders import Page
from agent.rag.retrieval import HybridRetriever
from agent.rag.store import ChunkStore
from agent.schemas.video_spec import StepCardScene
from agent.settings import REPO_ROOT
from agent.tests.conftest import SOURCES


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Take 500 mg every 8 hours", [Quantity(500, "mg"), Quantity(8, "h")]),
        ("Scrub for twenty seconds", [Quantity(20, "s")]),
        ("იხეხეთ ოცი წამის განმავლობაში", [Quantity(20, "s")]),
        ("მიიღეთ 500 მგ ყოველ 8 საათში", [Quantity(500, "mg"), Quantity(8, "h")]),
        ("დღეში სამჯერ", [Quantity(3, "times")]),
        ("3 times a day", [Quantity(3, "times")]),
        ("twice daily", [Quantity(2, "times")]),
        ("twenty five minutes", [Quantity(25, "min")]),
        ("at 08:00", [Quantity(480, "clock")]),
        ("above 38 °C", [Quantity(38, "c")]),
        ("1,5 ml", [Quantity(1.5, "ml")]),
    ],
)
def test_quantities_en_ka(text: str, expected: list[Quantity]) -> None:
    assert quantities(text) == expected


def test_missing_quantities_units_must_match() -> None:
    ev = "Take paracetamol 500 mg every 6 hours. 5. Dry your hands."
    assert missing_quantities("Take 500 mg every 6 hours", ev) == []
    assert missing_quantities("Take 1000 mg", ev) == [Quantity(1000, "mg")]
    assert missing_quantities("Scrub for 5 seconds", ev) == [Quantity(5, "s")]  # "5." is a list index
    assert missing_quantities("Use one towel", ev) == []  # a bare "one" is ignored
    assert str(Quantity(1.5, "ml")) == "1.5 ml" and str(Quantity(3, None)) == "3"


def test_polarity_and_clauses() -> None:
    assert is_negated("Do not drive") and is_negated("არ მართოთ") and is_negated("Never skip")
    assert not is_negated("Drive carefully") and not is_negated("არასწორი")  # word boundary in ka
    quote = "Use the hand-wash sink only — never wash your hands in a food preparation sink."
    assert closest_clause("Use the hand-wash sink only.", quote) == "Use the hand-wash sink only"
    assert check_claim("Use the hand-wash sink only.", quote, quote).ok
    bad = check_claim("Wash your hands in a food preparation sink.", quote, quote)
    assert not bad.ok and bad.gate == "polarity"
    assert closest_clause("x", "single clause") == "single clause"


def test_names_gate_glossary_and_drugs() -> None:
    ev = "Take paracetamol 500 mg. Keep the wound dry."
    assert missing_names("Take paracetamol", ev) == []
    assert missing_names("მიიღეთ პარაცეტამოლი", ev) == []  # cross-language glossary
    assert missing_names("Take ibuprofen", ev) == ["ibuprofen"]
    assert missing_names("Take amoxycillin", "Take amoxicillin 500 mg") == []  # fuzzy drug match
    assert missing_names("Take ciprofloxacin", ev) == ["ciprofloxacin"]
    g = check_claim("Apply cream to the eye", ev, None)
    assert not g.ok and g.gate == "names"
    assert check_claim("Take 1000 mg", ev, None).gate == "numbers"


def test_translation_gates() -> None:
    assert check_translation("Scrub for 20 seconds.", "იხეხეთ 20 წამი.", "Scrub for 20 seconds.") == []
    probs = check_translation("Do not drive for 1 week.", "მართეთ 2 კვირა.", "Drive for 2 weeks.")
    assert any("numbers" in p for p in probs) and any("negation" in p for p in probs)
    assert check_translation("Take ibuprofen", "მიიღეთ პარაცეტამოლი", "Take paracetamol")


def test_mutation_suite_offline_gates() -> None:
    cases = json.loads((REPO_ROOT / "data/fixtures/evals/mutations.json").read_text("utf-8"))["cases"]
    s = summarize(run_offline(cases))
    # Deterministic gates alone must catch every number/dose/drug corruption (en + ka).
    for kind in ("wrong_number", "wrong_dose", "wrong_drug", "wrong_number_ka"):
        assert s["by_kind"][kind]["recall"] >= 0.8, kind
    assert s["precision"] >= 0.9
    report = write_report({"gates only": s}, {})
    assert "| gates only | 20 |" in report and "No production runs" in report
    ok, why = gates_only("Scrub for 5 seconds.", (SOURCES / "handwashing-sop-en.md").read_text("utf-8"))
    assert not ok and "5 s" in why


def _retriever(tmp_path: Path, router: LLMRouter) -> HybridRetriever:
    text = (SOURCES / "discharge-knee-en.md").read_text("utf-8")
    docs = chunk_pages([Page(1, text)], project_id="fc", doc_id="dis", language="en")
    emb = Embedder(router, None)
    vecs, _ = emb.embed([d.page_content for d in docs], "RETRIEVAL_DOCUMENT")
    store = ChunkStore(tmp_path / "chroma", tmp_path / "fc", "fc")
    store.add(docs, vecs)
    r = HybridRetriever(store=store, embedder=emb)
    r.refresh()
    return r


def _scene(narration: str) -> StepCardScene:
    return StepCardScene(id="s1", template="step_card", step_no=1, total_steps=1, icon="pill", text="Medicine",
                         narration=narration, evidence=["dis:1:0", "nope:1:9"], duration_s=5)  # fmt: skip


def test_check_scene_gates_override_llm(tmp_path: Path, router: LLMRouter) -> None:
    r = _retriever(tmp_path, router)
    fake: Any = router.backend
    fake.responses["claim_extraction"] = lambda req: {
        "claims": [{"text": req.prompt.split("Narration: ")[1].split("\n")[0], "kind": "number"}]
    }
    fake.responses["fact_check_verdict"] = lambda req: {
        "verdicts": [{"claim_index": 0, "verdict": "supported", "chunk_id": "dis:1:0",
                      "quote": "Take paracetamol 500 mg every 6 hours as needed for pain.", "why": "stated"}]
    }  # fmt: skip
    good, usage = check_scene(_scene("Take paracetamol 500 mg every 6 hours."), r, router)
    assert good.ok and usage.cost_usd > 0
    assert "nope:1:9" not in good.evidence_ids
    bad, _ = check_scene(_scene("Take paracetamol 1000 mg every 6 hours."), r, router)
    assert not bad.ok
    c = bad.claims[0]
    assert c.llm_verdict == "supported" and c.verdict == "unsupported" and c.gate == "numbers"
    assert "1000 mg" in bad.problems()[0]


def test_check_scene_without_claims_or_verdicts(tmp_path: Path, router: LLMRouter) -> None:
    r = _retriever(tmp_path, router)
    fake: Any = router.backend
    fake.responses["claim_extraction"] = {"claims": []}
    rep, _ = check_scene(_scene("Hello."), r, router)
    assert rep.ok and rep.claims == []
    fake.responses["claim_extraction"] = {"claims": [{"text": "Rest", "kind": "instruction"}]}
    fake.responses["fact_check_verdict"] = {"verdicts": []}
    rep, _ = check_scene(_scene("Rest."), r, router)
    assert not rep.ok and rep.claims[0].verdict == "unsupported"


def test_quiz_scene_adds_correct_answer(tmp_path: Path, router: LLMRouter) -> None:
    from agent.schemas.video_spec import QuizQuestionScene

    seen: list[str] = []

    def claims(req: GenRequest) -> dict[str, Any]:
        seen.append(req.prompt)
        return {"claims": []}

    fake: Any = router.backend
    fake.responses["claim_extraction"] = claims
    q = QuizQuestionScene(id="q", template="quiz_question", question="Dose?", options=["500 mg", "1000 mg"],
                          correct_index=0, countdown_s=4, narration="Quiz.", evidence=[], duration_s=8)  # fmt: skip
    check_scene(q, _retriever(tmp_path, router), router)
    assert "Correct answer: 500 mg" in seen[0]


def test_fact_report_merge_signature_counts() -> None:
    a = SceneReport(scene_id="s1", ok=True)
    b = SceneReport(scene_id="s2", ok=False, translation_problems=["numbers differ"])
    rep = FactReport(scenes=[a, b])
    assert not rep.ok and [s.scene_id for s in rep.failing()] == ["s2"]
    assert rep.signature() == "s2:1"
    fixed = rep.merged([SceneReport(scene_id="s2", ok=True)], ["s2", "s1"])
    assert fixed.ok and [s.scene_id for s in fixed.scenes] == ["s2", "s1"]
    assert rep.counts() == {}


def test_disclaimer_is_policy_not_a_claim(tmp_path: Path, router: LLMRouter) -> None:
    from agent.schemas.video_spec import DisclaimerScene

    d = DisclaimerScene(id="d", template="disclaimer", heading="Follow your doctor", text="This summarises the document.",
                        narration="Follow your doctor's instructions.", evidence=[], duration_s=5)  # fmt: skip
    rep, usage = check_scene(d, _retriever(tmp_path, router), router)
    assert rep.ok and rep.claims == [] and usage.cost_usd == 0
