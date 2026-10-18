# ADR 0001 — Stack and repository layout

- Status: accepted
- Date: 2026-09-15

## Context

We generate short (30–60 s) instructional videos from a user's source document, with an agent that
plans, writes, fact-checks, narrates and renders. Rendering must be deterministic and fast; the
agent needs durable, resumable state and human checkpoints; the UI is a chat plus a video preview.

## Decision

A monorepo with three parts:

| part | tech | why |
|---|---|---|
| `video/` | Remotion 4 + React + TypeScript | data-driven templates as React components, frame-exact, programmatic `renderMedia` with progress callbacks |
| `agent/` | Python 3.12 (uv), FastAPI, LangGraph, LangChain (retrieval pieces), `google-genai` on Vertex AI | LangGraph gives checkpointed state, `interrupt()` for human review and `Send` map-reduce; Python has the best document-loading and RAG ecosystem |
| `web/` | Vite + React + TypeScript | small two-pane UI fed by SSE |

- **One contract:** Pydantic models in `agent/` are the source of truth for the video spec; JSON Schema
  is exported and TypeScript types + zod validators are generated for `video/`.
- **One model SDK:** `google-genai` (Vertex mode) for chat, structured output, TTS, transcription and
  embeddings, behind a single router. Model names live only in `config/models.yaml`.
- **Auth:** Application Default Credentials (`gcloud auth application-default login` or a service
  account). No API keys anywhere.
- **Languages:** Georgian (`ka`) and English (`en`).
- **Environment isolation:** Python in the repo `.venv` via uv (uv-managed CPython only); Node packages
  in npm workspaces; system ffmpeg by absolute path from `FFMPEG_DIR`.

## Consequences

- Two toolchains (uv + npm) and a codegen step; CI fails when generated files are stale.
- The renderer runs as a Node subprocess of the agent and reports progress as JSON lines.
