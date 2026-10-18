# InstructVid

Turn a source document (SOP, safety procedure, discharge instructions) into a fact-checked
**30–60 s instructional video** by chatting with an agent: flat motion graphics, Georgian or
English narration, burned-in captions and quiz checkpoints.

Status: scaffolding. See [docs/brief.md](docs/brief.md) for the product spec.

## Layout

| dir | what |
|---|---|
| `agent/` | Python 3.12 agent (uv): FastAPI + LangGraph + Gemini on Vertex AI |
| `video/` | Remotion project: scene templates and the render worker |
| `web/` | Vite + React chat and video preview UI |
| `config/` | `models.yaml` (the only place model names appear), `app.yaml` |
| `data/` | catalog data, glossaries, fixtures (runtime data is gitignored) |
| `docs/` | brief, ADRs |

## Setup

```powershell
# Python (uv-managed CPython 3.12 -> .venv)
uv sync
# Node workspaces (video + web)
npm install
# Vertex AI via Application Default Credentials
gcloud auth application-default login
copy .env.example .env   # then set GOOGLE_CLOUD_PROJECT
```

## Licence note

Rendering uses [Remotion](https://remotion.dev), which is free for individuals and companies of up
to 3 people; commercial deployments need a company licence — see
[docs/adr/0002-remotion-licence.md](docs/adr/0002-remotion-licence.md).

## Checks

```powershell
uv run ruff check . ; uv run mypy ; uv run pytest
npm run lint ; npm run typecheck ; npm test
```
