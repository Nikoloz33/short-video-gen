# InstructVid — project guidelines

Chat agent that turns a source document (SOP, safety procedure, discharge instructions) into a
fact-checked 30–60 s instructional video: flat motion graphics, Georgian or English narration,
burned-in captions, quiz checkpoints. Product spec: `docs/brief.md` (single source of truth).

## Layout
- `agent/` — Python 3.12 package (uv): settings, config, logging; graph, RAG, TTS, API land here.
- `video/` — Remotion 4 project (npm workspace): templates, render scripts.
- `web/` — Vite + React UI (npm workspace).
- `config/models.yaml` — the ONLY place model names appear. `config/app.yaml` — paces, caps, presets.
- `docs/` — brief + ADRs.

## Environment rules (isolated — never install globally)
- Python: `uv sync` creates `.venv` with a uv-managed CPython 3.12 (`python-preference = only-managed`
  in pyproject; the system 3.12 is broken). Run everything via `uv run …`. `uv` lives in
  `%USERPROFILE%\.local\bin` — in Git Bash: `export PATH="$HOME/.local/bin:$PATH"` (the home path has a space).
- Node: npm workspaces at the root (`npm install` once). Never `npm i -g`.
- All `remotion` / `@remotion/*` packages stay on the SAME exact version (4.0.530).
- TypeScript stays < 6.1 (typescript-eslint peer range).
- ffmpeg/ffprobe by absolute path: `FFMPEG_DIR` in `.env` (default `C:\ffmpeg-7.1.1-essentials_build\bin`).
- Vertex AI via ADC only (`gcloud auth application-default login`); `.env` holds `GOOGLE_CLOUD_PROJECT`,
  `GOOGLE_CLOUD_LOCATION=eu`, `GOOGLE_GENAI_USE_VERTEXAI=True`. Never commit `.env` or credentials.

## Conventions
- Python: ruff (lint + format), mypy `--strict`, pytest with coverage ≥ 85 % of `agent/`;
  structlog with `thread_id` bound (`agent.logging.bound_thread`), never `print`.
  CLIs call `agent.logging.configure()` (reconfigures stdout/stderr to UTF-8 for Georgian).
- TypeScript: strict, eslint (root `eslint.config.js`), prettier (root `.prettierrc.json`), vitest.
- Video: 30 fps; `secToFrame()` in `video/src/lib/time.ts` is the one place seconds become frames.
- Languages: `ka` and `en` only.

## Commands
| command | what |
|---|---|
| `uv run ruff check . ; uv run ruff format --check . ; uv run mypy ; uv run pytest` | Python checks |
| `npm run lint ; npm run format:check ; npm run typecheck ; npm test` | TS checks (all workspaces) |
| `npm run render:smoke -w video` | bundle + tiny render + ffprobe check |
| `npm run studio -w video` | Remotion Studio |
| `npm run dev -w web` | web UI dev server |

## Tooling gotchas
- Bash heredocs mangle `${}`, backticks and `\n`: write scripts with the editor tools instead.
- Paths contain spaces: quote them; run ffmpeg with relative paths from the repo root.
- Remotion bundles copy `video/public/` into `%TEMP%`; `bundleProject()` deletes its bundle on exit.
