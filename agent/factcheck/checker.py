"""Per-scene fact check: claims (Flash) -> evidence (project RAG only) -> verdict (Argon) -> gates."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agent.factcheck.gates import check_claim
from agent.llm.router import LLMRouter
from agent.llm.usage import Usage, merge_usage
from agent.prompts import load_prompt, source_block
from agent.rag.retrieval import HybridRetriever
from agent.schemas.llm_io import ClaimKind, Claims, Verdict, Verdicts
from agent.schemas.video_spec import Scene
from agent.script import scene_texts

MAX_EVIDENCE = 10


class ClaimReport(BaseModel):
    text: str
    kind: ClaimKind
    verdict: Verdict
    llm_verdict: Verdict
    chunk_id: str | None = None
    quote: str | None = None
    why: str = ""
    gate: str | None = Field(default=None, description="Deterministic gate that overrode the LLM")


class SceneReport(BaseModel):
    scene_id: str
    ok: bool
    claims: list[ClaimReport] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    translation_problems: list[str] = Field(default_factory=list)

    def problems(self) -> list[str]:
        out = [f'"{c.text}": {c.verdict} — {c.why}' for c in self.claims if c.verdict != "supported"]
        return out + self.translation_problems


class FactReport(BaseModel):
    scenes: list[SceneReport] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(s.ok and not s.translation_problems for s in self.scenes)

    def failing(self) -> list[SceneReport]:
        return [s for s in self.scenes if not s.ok or s.translation_problems]

    def signature(self) -> str:
        """Identifies the failure set: an unchanged signature after a fix means the fix loop is stuck."""
        return "|".join(sorted(f"{s.scene_id}:{len(s.problems())}" for s in self.failing()))

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for s in self.scenes:
            for c in s.claims:
                out[c.verdict] = out.get(c.verdict, 0) + 1
        return out

    def merged(self, updates: list[SceneReport], order: list[str]) -> FactReport:
        by_id = {s.scene_id: s for s in self.scenes}
        for u in updates:
            by_id[u.scene_id] = u
        return FactReport(scenes=[by_id[i] for i in order if i in by_id])


def check_scene(scene: Scene, retriever: HybridRetriever, router: LLMRouter) -> tuple[SceneReport, Usage]:
    texts = scene_texts(scene)
    prompt = load_prompt("claims").render(
        template=scene.template, texts=" | ".join(texts), narration=scene.narration
    )
    if scene.template in ("quiz_question", "quiz_answer"):
        correct = scene.options[scene.correct_index]
        prompt += f"\nCorrect answer: {correct}"
    claims_r = router.structured("claim_extraction", prompt, Claims)
    usage = claims_r.usage
    claims = claims_r.value.claims
    if not claims:
        return SceneReport(scene_id=scene.id, ok=True), usage

    store = retriever.store
    ev_ids: list[str] = [e for e in scene.evidence if store.chunk(e) is not None]
    for c in claims:
        docs, u = retriever.search(c.text, k=3)
        usage = merge_usage(usage, u)
        ev_ids += [str(d.id) for d in docs]
    ev_ids = list(dict.fromkeys(ev_ids))[:MAX_EVIDENCE]
    chunks = [d for i in ev_ids if (d := store.chunk(i)) is not None]
    evidence_text = "\n".join(d.page_content for d in chunks)

    claim_list = "\n".join(f"{i}. [{c.kind}] {c.text}" for i, c in enumerate(claims))
    evidence = (
        "\n".join(source_block(d.page_content, f"CHUNK {d.id}") for d in chunks) or "(no evidence found)"
    )
    vr = router.structured(
        "fact_check_verdict", load_prompt("verdict").render(claims=claim_list, evidence=evidence), Verdicts
    )
    usage = merge_usage(usage, vr.usage)
    by_index = {v.claim_index: v for v in vr.value.verdicts}

    reports: list[ClaimReport] = []
    for i, c in enumerate(claims):
        v = by_index.get(i)
        llm: Verdict = v.verdict if v else "unsupported"
        quote = v.quote if v else None
        gate = check_claim(c.text, evidence_text, quote)
        final: Verdict = llm if gate.ok else ("contradicts" if gate.gate == "polarity" else "unsupported")
        reports.append(
            ClaimReport(
                text=c.text,
                kind=c.kind,
                verdict=final,
                llm_verdict=llm,
                chunk_id=v.chunk_id if v else None,
                quote=quote,
                why=(gate.why or "") if not gate.ok else (v.why if v else "no verdict returned"),
                gate=gate.gate,
            )
        )
    ok = all(r.verdict == "supported" for r in reports)
    return SceneReport(scene_id=scene.id, ok=ok, claims=reports, evidence_ids=ev_ids), usage
