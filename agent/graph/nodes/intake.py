"""intake: language/requirements, scope + safety screen, PII screen of the message.
ingest_source: chunk + embed + index uploaded sources not indexed yet."""

from __future__ import annotations

from typing import Any

from agent.graph.deps import Deps, say, status
from agent.graph.nodes.common import history_text, last_user_text
from agent.graph.state import GraphState
from agent.privacy.pii import regex_scrub
from agent.prompts import load_prompt
from agent.rag.chunking import chunk_pages
from agent.rag.loaders import Page
from agent.schemas.llm_io import IntakeResult


def make_intake(deps: Deps) -> Any:
    def intake(state: GraphState) -> dict[str, Any]:
        pid = state["project_id"]
        sources = deps.projects.sources(pid)
        # The user's own message is screened too: personal data never reaches the model.
        message, _ = regex_scrub(last_user_text(state))
        src_desc = ", ".join(f"{s.title} ({s.lang})" for s in sources) or "none"
        r = deps.router.structured(
            "intake",
            load_prompt("intake").render(
                sources=src_desc, history=history_text(state.get("messages", [])[:-1]), message=message
            ),
            IntakeResult,
        )
        res = r.value
        out: dict[str, Any] = {"usage": r.usage.model_dump()}
        if not res.in_scope:
            return {**out, **say(res.refusal_reason or res.reply), **status("refused"), "route": "end"}
        if not sources:
            return {**out, **say(res.reply), **status("need_source"), "route": "end"}
        prev = state.get("request", {})
        src_lang = sources[0].lang
        request = {
            "target_lang": res.target_lang or prev.get("target_lang") or src_lang,
            "target_sec": int(res.target_sec or prev.get("target_sec") or 45),
            "audience": res.audience or prev.get("audience") or "workplace",
            "quiz_count": res.quiz_count if res.quiz_count is not None else prev.get("quiz_count", 1),
            "source_lang": src_lang,
        }
        request["target_sec"] = max(30, min(60, request["target_sec"]))
        return {**out, **say(res.reply), **status("planning"), "request": request, "route": "ingest_source"}

    return intake


def make_ingest_source(deps: Deps) -> Any:
    def ingest_source(state: GraphState) -> dict[str, Any]:
        pid = state["project_id"]
        done = set(state.get("indexed_docs", []))
        store = deps.store(pid)
        new_docs: list[str] = []
        total_chunks = 0
        usage: dict[str, Any] = {}
        for doc in deps.projects.sources(pid):
            if doc.doc_id in done:
                continue
            pages = [Page(p["number"], p["text"]) for p in doc.pages]
            chunks = chunk_pages(pages, project_id=pid, doc_id=doc.doc_id, language=doc.lang)
            vectors, u = deps.embedder.embed([c.page_content for c in chunks], "RETRIEVAL_DOCUMENT")
            store.add(chunks, vectors)
            usage = u.model_dump()
            new_docs.append(doc.doc_id)
            total_chunks += len(chunks)
        deps.retriever(pid).refresh()
        card = {"kind": "source", "docs": len(done) + len(new_docs), "new_chunks": total_chunks}
        out: dict[str, Any] = {"indexed_docs": sorted(done | set(new_docs)), "usage": usage}
        if new_docs:
            out.update(say(f"Indexed {total_chunks} passages from your source.", card))
        return out

    return ingest_source
