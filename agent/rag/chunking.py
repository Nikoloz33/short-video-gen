"""Structure-first chunking: split by headings / numbered steps, then size-limit with overlap.

Chunk ids are stable: `<doc_id>:<page>:<index>`. Metadata: project_id, doc_id, page, section,
step_no, language, char_span.
"""

from __future__ import annotations

import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from agent.rag.loaders import Page

# ~400 tokens at ~4 chars/token, ~15 % overlap.
CHUNK_CHARS = 1600
OVERLAP_CHARS = 240

_HEADING = re.compile(r"^(#{1,6}\s+.+|[A-ZА-ЯႠ-Ⴥ][A-ZА-ЯႠ-Ⴥ0-9 ,&/()-]{3,}:?|.{2,80}:)\s*$")
_STEP = re.compile(r"^\s*(?:step\s*|ნაბიჯი\s*)?(\d{1,2})[.)]\s+\S", re.IGNORECASE)


def _blocks(text: str) -> list[tuple[str, int | None, str, int]]:
    """(section, step_no, block text, start offset) — a new block at each heading or numbered step."""
    blocks: list[tuple[str, int | None, str, int]] = []
    section = ""
    step: int | None = None
    buf: list[str] = []
    start = 0
    offset = 0

    def flush(at: int) -> None:
        nonlocal buf, start
        body = "\n".join(buf).strip()
        if body:
            blocks.append((section, step, body, start))
        buf = []
        start = at

    for line in text.split("\n"):
        stripped = line.strip()
        m_step = _STEP.match(line)
        if stripped and _HEADING.match(stripped) and not m_step and len(stripped) < 90:
            flush(offset)
            section, step = stripped.lstrip("#").strip().rstrip(":"), None
            buf.append(line)
        elif m_step:
            flush(offset)
            step = int(m_step.group(1))
            buf.append(line)
        else:
            buf.append(line)
        offset += len(line) + 1
    flush(offset)
    return blocks


def chunk_pages(pages: list[Page], *, project_id: str, doc_id: str, language: str) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_CHARS, chunk_overlap=OVERLAP_CHARS)
    docs: list[Document] = []
    for page in pages:
        index = 0
        # Merge tiny neighbouring blocks (one-line steps) up to the chunk size: fewer, richer chunks.
        merged: list[tuple[str, int | None, str, int]] = []
        for sec, step, body, start in _blocks(page.text):
            if merged and len(merged[-1][2]) + len(body) < CHUNK_CHARS // 2 and merged[-1][0] == sec:
                psec, pstep, pbody, pstart = merged[-1]
                merged[-1] = (psec, pstep, f"{pbody}\n{body}", pstart)
            else:
                merged.append((sec, step, body, start))
        for sec, step, body, start in merged:
            for piece in splitter.split_text(body):
                at = page.text.find(piece[:40], start)
                at = start if at < 0 else at
                docs.append(
                    Document(
                        page_content=piece,
                        id=f"{doc_id}:{page.number}:{index}",
                        metadata={
                            "chunk_id": f"{doc_id}:{page.number}:{index}",
                            "project_id": project_id,
                            "doc_id": doc_id,
                            "page": page.number,
                            "section": sec,
                            "step_no": step if step is not None else -1,
                            "language": language,
                            "char_span": f"{at}-{at + len(piece)}",
                        },
                    )
                )
                index += 1
    return docs
