"""FastAPI app.

    uv run uvicorn agent.api.app:app --port 8000          (APP_FAKE=1 for fake models)

All routes are under /api and need `Authorization: Bearer <APP_TOKEN>` (media URLs may pass
`?token=` because <video> elements cannot send headers). Long operations stream Server-Sent Events:
token, card, status, render_progress, render_done, fact_progress, node, awaiting_review, error, done.
"""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import anyio
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agent.graph.runner import Runner, build_deps
from agent.logging import configure, get_logger
from agent.rag.loaders import UnsupportedFileError
from agent.schemas.video_spec import VideoSpec
from agent.script import scene_texts
from agent.settings import REPO_ROOT, Settings, get_settings

log = get_logger("api")
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
FILES = {"mp4": "video.mp4", "srt": "video.srt", "vtt": "video.vtt", "quiz": "quiz.json"}


class CreateProject(BaseModel):
    title: str = "Untitled"


class SendMessage(BaseModel):
    text: str


class Resume(BaseModel):
    action: Literal[
        "approve", "edit", "regenerate",
        "keep_claim", "remove_claim", "keep_flagged", "remove_flagged", "fix_flagged",
    ]  # fmt: skip
    text: str | None = None
    #: For keep_claim / remove_claim: which flagged claim.
    scene_id: str | None = None
    index: int | None = None


def create_app(settings: Settings | None = None, runner: Runner | None = None) -> FastAPI:
    settings = settings or get_settings()
    state: dict[str, Runner] = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        configure()
        state["runner"] = runner or Runner(build_deps(settings))
        yield
        if runner is None:
            state["runner"].close()

    app = FastAPI(title="InstructVid API", lifespan=lifespan)

    def get_runner() -> Runner:
        return state["runner"]

    def auth(
        authorization: str | None = Header(default=None), token: str | None = Query(default=None)
    ) -> str:
        supplied = token or (authorization or "").removeprefix("Bearer ").strip()
        if supplied != settings.app_token:
            raise HTTPException(401, "missing or invalid token")
        return "user"

    def project_or_404(r: Runner, pid: str) -> None:
        if not r.deps.projects.exists(pid):
            raise HTTPException(404, "no such project")

    def sse(r: Runner, pid: str, events: Iterator[dict[str, Any]]) -> EventSourceResponse:
        lock = r.lock(pid)
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "this project is already running")

        # The whole run happens on ONE worker thread (context variables — thread id, spend budget —
        # must not hop threads); events reach the response through a queue.
        q: queue.Queue[dict[str, Any] | None] = queue.Queue()

        def produce() -> None:
            try:
                for ev in events:
                    q.put(ev)
            except Exception as e:  # pragma: no cover - the runner converts errors to events
                q.put({"type": "error", "code": "run_failed", "message": str(e)})
            finally:
                lock.release()
                q.put(None)

        threading.Thread(target=produce, name=f"run-{pid}", daemon=True).start()

        async def stream() -> AsyncIterator[dict[str, str]]:
            while True:
                ev = await anyio.to_thread.run_sync(q.get)
                if ev is None:
                    return
                yield {"event": str(ev.get("type", "message")), "data": json.dumps(ev, ensure_ascii=False)}

        return EventSourceResponse(stream(), ping=15)

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "fake": settings.app_fake}

    @app.get("/api/projects", dependencies=[Depends(auth)])
    def list_projects(r: Runner = Depends(get_runner)) -> list[dict[str, Any]]:
        return r.deps.projects.list_projects()

    @app.post("/api/projects", dependencies=[Depends(auth)])
    def create_project(body: CreateProject, r: Runner = Depends(get_runner)) -> dict[str, Any]:
        pid = r.deps.projects.create(body.title)
        return {"id": pid, "title": body.title}

    @app.get("/api/projects/{pid}", dependencies=[Depends(auth)])
    def snapshot(pid: str, r: Runner = Depends(get_runner)) -> dict[str, Any]:
        project_or_404(r, pid)
        values = r.state(pid)
        messages: list[dict[str, Any]] = []
        for m in values.get("messages", []):
            if isinstance(m, HumanMessage):
                messages.append({"role": "user", "text": str(m.content)})
            elif isinstance(m, AIMessage):
                messages.append(
                    {"role": "agent", "text": str(m.content), "card": m.additional_kwargs.get("card")}
                )
        spec = values.get("spec")
        outline = None
        if spec:
            s = VideoSpec.model_validate(spec)
            outline = {
                "version": s.version,
                "title": s.title,
                "lang": s.lang,
                "total_s": round(s.total_s, 2),
                "scenes": [
                    {
                        "id": x.id,
                        "template": x.template,
                        "texts": scene_texts(x),
                        "narration": x.narration,
                        "duration_s": x.duration_s,
                    }
                    for x in s.scenes
                ],
            }
        usage = values.get("usage") or {}
        return {
            "project": r.deps.projects.meta(pid),
            "status": values.get("status", "idle"),
            "messages": messages,
            "pending": r.pending_interrupt(pid),
            "can_retry": r.can_retry(pid),
            "spec": outline,
            "render": values.get("render"),
            "tts": values.get("tts_stats"),
            "versions": r.deps.projects.versions(pid),
            "sources": [
                {
                    "doc_id": d.doc_id,
                    "title": d.title,
                    "lang": d.lang,
                    "redactions": d.redactions,
                    "removed_lines": len(d.removed_lines),
                }
                for d in r.deps.projects.sources(pid)
            ],
            "cost_usd": round(sum(x.get("cost_usd", 0.0) for x in usage.get("roles", [])), 6),
            "usage": usage.get("roles", []),
        }

    @app.post("/api/projects/{pid}/sources", dependencies=[Depends(auth)])
    async def upload(
        pid: str, file: UploadFile = File(...), r: Runner = Depends(get_runner)
    ) -> dict[str, Any]:
        project_or_404(r, pid)
        data = await file.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "file too large (15 MB max)")
        try:
            doc, _usage = r.deps.projects.add_source(pid, file.filename or "upload.txt", data, r.deps.router)
        except UnsupportedFileError as e:
            raise HTTPException(415, str(e)) from e
        return {
            "doc_id": doc.doc_id,
            "title": doc.title,
            "lang": doc.lang,
            "chars": len(doc.text),
            "redactions": doc.redactions,
            "removed_lines": doc.removed_lines,
        }

    @app.post("/api/projects/{pid}/messages", dependencies=[Depends(auth)])
    def send_message(pid: str, body: SendMessage, r: Runner = Depends(get_runner)) -> EventSourceResponse:
        project_or_404(r, pid)
        if not body.text.strip():
            raise HTTPException(422, "empty message")
        return sse(r, pid, r.run(pid, message=body.text))

    @app.post("/api/projects/{pid}/resume", dependencies=[Depends(auth)])
    def resume(
        pid: str, body: Resume, user: str = Depends(auth), r: Runner = Depends(get_runner)
    ) -> EventSourceResponse:
        project_or_404(r, pid)
        if r.pending_interrupt(pid) is None:
            raise HTTPException(409, "nothing is waiting for review")
        return sse(
            r,
            pid,
            r.run(pid, resume={**body.model_dump(exclude_none=True), "text": body.text or "", "user": user}),
        )

    @app.post("/api/projects/{pid}/retry", dependencies=[Depends(auth)])
    def retry(pid: str, r: Runner = Depends(get_runner)) -> EventSourceResponse:
        """Continue a run that stopped on an error (e.g. a provider 429) from its last checkpoint."""
        project_or_404(r, pid)
        if not r.can_retry(pid):
            raise HTTPException(409, "nothing to retry")
        return sse(r, pid, r.run(pid, retry=True))

    @app.get("/api/projects/{pid}/versions/{version}/{preset}/{kind}", dependencies=[Depends(auth)])
    def download(
        pid: str,
        version: int,
        preset: Literal["preview", "final"],
        kind: str,
        r: Runner = Depends(get_runner),
    ) -> FileResponse:
        project_or_404(r, pid)
        if kind not in FILES:
            raise HTTPException(404, "unknown file")
        path = r.deps.projects.version_dir(pid, version) / preset / FILES[kind]
        if not path.is_file():
            raise HTTPException(404, "not rendered")
        media = {
            "mp4": "video/mp4",
            "srt": "application/x-subrip",
            "vtt": "text/vtt",
            "quiz": "application/json",
        }[kind]
        return FileResponse(path, media_type=media, filename=f"{pid}-v{version}-{preset}-{FILES[kind]}")

    dist = REPO_ROOT / "web" / "dist"
    if Path(dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app


app = create_app()
