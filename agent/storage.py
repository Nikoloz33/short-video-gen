"""On-disk layout of a project (thread):

data/projects/<id>/
  project.json            title, created, settings
  raw/<doc_id><ext>       original uploads (local only; deleted after the retention period)
  sources/<doc_id>.json   cleaned, PII-scrubbed text pages + redaction report
  chunks.json             indexed chunks (BM25 + citations)
  audio/<hash>.wav        narration clips (cache, shared across versions)
  versions/v<N>/spec.json + preview/ + final/   one folder per spec version
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from agent.llm.router import LLMRouter
from agent.llm.usage import Usage
from agent.privacy.pii import Redaction, scrub
from agent.rag.hygiene import normalize, strip_injections
from agent.rag.loaders import SUPPORTED, UnsupportedFileError, detect_lang, load_pages
from agent.schemas.video_spec import VideoSpec

_ID = re.compile(r"^[a-z0-9]{6,32}$")


@dataclass
class SourceDoc:
    doc_id: str
    title: str
    lang: str
    pages: list[dict[str, Any]]
    redactions: list[dict[str, str]] = field(default_factory=list)
    removed_lines: list[str] = field(default_factory=list)
    created: float = field(default_factory=time.time)

    @property
    def text(self) -> str:
        return "\n\n".join(p["text"] for p in self.pages)


class ProjectStore:
    def __init__(self, data_dir: Path) -> None:
        self.root = data_dir / "projects"
        self.root.mkdir(parents=True, exist_ok=True)

    def new_id(self) -> str:
        return secrets.token_hex(6)

    def dir(self, project_id: str) -> Path:
        if not _ID.match(project_id):
            raise ValueError(f"bad project id {project_id!r}")
        return self.root / project_id

    def exists(self, project_id: str) -> bool:
        return _ID.match(project_id) is not None and (self.dir(project_id) / "project.json").exists()

    def create(self, title: str = "Untitled", owner: str = "local") -> str:
        pid = self.new_id()
        d = self.dir(pid)
        d.mkdir(parents=True)
        (d / "project.json").write_text(
            json.dumps({"id": pid, "title": title, "owner": owner, "created": time.time()}), "utf-8"
        )
        return pid

    def meta(self, project_id: str) -> dict[str, Any]:
        data: dict[str, Any] = json.loads((self.dir(project_id) / "project.json").read_text("utf-8"))
        return data

    def list_projects(self) -> list[dict[str, Any]]:
        out = [self.meta(p.name) for p in self.root.iterdir() if (p / "project.json").exists()]
        return sorted(out, key=lambda m: -float(m["created"]))

    # ---- sources ----------------------------------------------------------------------------------
    def add_source(
        self, project_id: str, filename: str, data: bytes, router: LLMRouter | None = None
    ) -> tuple[SourceDoc, Usage]:
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED:
            raise UnsupportedFileError(f"unsupported file type {suffix!r}; use {', '.join(SUPPORTED)}")
        d = self.dir(project_id)
        stem = re.sub(r"[^a-z0-9]+", "-", Path(filename).stem.lower()).strip("-")[:24] or "doc"
        doc_id = f"{stem}-{secrets.token_hex(2)}"
        raw = d / "raw" / f"{doc_id}{suffix}"
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_bytes(data)
        pages_in = load_pages(raw)
        pages: list[dict[str, Any]] = []
        redactions: list[Redaction] = []
        removed: list[str] = []
        usage = Usage()
        for p in pages_in:
            text, dropped = strip_injections(normalize(p.text))
            removed += dropped
            clean, found, u = scrub(text, router)
            from agent.llm.usage import merge_usage

            usage = merge_usage(usage, u)
            redactions += found
            pages.append({"number": p.number, "text": clean})
        lang = detect_lang(" ".join(p["text"] for p in pages))
        doc = SourceDoc(
            doc_id=doc_id,
            title=Path(filename).name,
            lang=lang,
            pages=pages,
            redactions=[asdict(r) for r in redactions],
            removed_lines=removed,
        )
        src = d / "sources" / f"{doc_id}.json"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(json.dumps(asdict(doc), ensure_ascii=False, indent=1), "utf-8")
        return doc, usage

    def sources(self, project_id: str) -> list[SourceDoc]:
        folder = self.dir(project_id) / "sources"
        if not folder.exists():
            return []
        docs = [SourceDoc(**json.loads(p.read_text("utf-8"))) for p in folder.glob("*.json")]
        return sorted(docs, key=lambda s: s.created)

    def purge_raw(self, project_id: str, older_than_days: float) -> int:
        """Retention: delete raw uploads older than the setting. Returns files removed."""
        folder = self.dir(project_id) / "raw"
        n = 0
        cutoff = time.time() - older_than_days * 86400
        for f in folder.glob("*") if folder.exists() else []:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                n += 1
        return n

    # ---- versions ---------------------------------------------------------------------------------
    def version_dir(self, project_id: str, version: int) -> Path:
        return self.dir(project_id) / "versions" / f"v{version}"

    def save_spec(self, project_id: str, spec: VideoSpec) -> Path:
        d = self.version_dir(project_id, spec.version)
        d.mkdir(parents=True, exist_ok=True)
        p = d / "spec.json"
        p.write_text(spec.model_dump_json(indent=1), "utf-8")
        return p

    def load_spec(self, project_id: str, version: int) -> VideoSpec:
        return VideoSpec.model_validate_json(
            (self.version_dir(project_id, version) / "spec.json").read_text("utf-8")
        )

    def record_approval(self, project_id: str, version: int, user: str) -> None:
        """Audit log: who approved which version for final export (append-only JSON lines)."""
        with (self.dir(project_id) / "audit.jsonl").open("a", encoding="utf-8") as f:
            f.write(
                json.dumps({"ts": time.time(), "event": "approve_final", "version": version, "user": user})
                + "\n"
            )

    def audit(self, project_id: str) -> list[dict[str, Any]]:
        p = self.dir(project_id) / "audit.jsonl"
        return [json.loads(line) for line in p.read_text("utf-8").splitlines()] if p.exists() else []

    def versions(self, project_id: str) -> list[dict[str, Any]]:
        """Every saved version with its rendered files (for the UI version selector)."""
        root = self.dir(project_id) / "versions"
        out: list[dict[str, Any]] = []
        for d in sorted(root.glob("v*"), key=lambda p: int(p.name[1:]) if p.name[1:].isdigit() else 0):
            if not d.name[1:].isdigit():
                continue
            entry: dict[str, Any] = {"version": int(d.name[1:]), "preview": None, "final": None}
            for preset in ("preview", "final"):
                if (d / preset / "video.mp4").exists():
                    entry[preset] = {k: (d / preset / f).exists() for k, f in
                                     (("mp4", "video.mp4"), ("srt", "video.srt"), ("vtt", "video.vtt"), ("quiz", "quiz.json"))}  # fmt: skip
            out.append(entry)
        return out

    def delete(self, project_id: str) -> None:
        shutil.rmtree(self.dir(project_id), ignore_errors=True)
