# InstructVid — project guidelines

Chat agent that turns a source document (SOP, safety procedure, discharge instructions) into a
fact-checked instructional video (30 s to 5 min): flat motion graphics, Georgian or English narration,
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
- Fonts: Noto Sans + Noto Sans Georgian, bundled in `video/public/fonts` (OFL) and loaded with
  `loadBundledFonts()`; CSS stack `FONT_STACK` in `video/src/theme/theme.ts`. Never a CDN.
- Theme: `DEFAULT_THEME` + `TENANT_THEMES` overrides via `resolveTheme(name, override)`.
- Icons: the LLM may only use names from `video/src/catalog/icons.json` (Lucide + 4 custom pictograms
  in `video/src/icons/custom.tsx`, tags in en/ka). Add an icon = add a catalog entry; the test checks
  it resolves.

## Agent (agent/)
- Graph: `agent/graph/build.py` wires nodes from `agent/graph/nodes/*` (factories over `Deps`, no
  globals). Routing functions only read state; nodes write a one-shot `route` hint that the
  `_clears_route` wrapper resets — `check_scene` (parallel `Send` branches) is registered unwrapped.
- Human checkpoints: `present_*` posts the card, `review_*` only calls `interrupt()` (nodes re-run
  from the top on resume — no side effects there). Resume payload `{action: approve|edit|regenerate, text, user}`; flagged claims are
  decided at the script review (`keep_claim`/`remove_claim` + `scene_id`/`index`, `keep_flagged`,
  `remove_flagged`, `fix_flagged` → `decide_claims` in `nodes/review.py`, audit-logged). Only ONE
  automatic fact-repair loop runs before the user sees the script.
- `Runner` (`agent/graph/runner.py`): SqliteSaver at `data/checkpoints.sqlite`, thread_id = project id,
  stream modes updates+custom, spend budget + thread id bound per run. A run must stay on ONE thread
  (context vars): the API runs it in a worker thread and pipes events through a queue.
- Models: only via `LLMRouter` roles. Both Flash and Argon returned 429 on the trial project (eu
  and global): Flash roles fall back to `fallback_reasoning` (Argon), Argon roles to `fallback_fast`
  (Flash), with a 5-min cooldown per model; SDK-internal retries are off. A run that still fails
  keeps its checkpoint: `Runner.run(retry=True)` / `POST /retry` / `agent.cli retry` continue it.
- Fact-check lessons from live runs: "stop" is not a negation ("hands stop germs"); polarity is
  compared per clause of the quote; translation name checks are one-directional (source names must
  survive; "Handwashing" becomes "ხელების დაბანა"); layout fixes get an explicit character target
  and their own loop budget (`layout_loops`).
- Writes happen in the source language; `translate` runs after fact-check (+ back-translation gates).
- Chat edits: `chat_edit` → `EditPlan` ops → `apply_edit` (`apply_ops`) → minimal recompute route.
- LLM drafts are flat (`agent/schemas/llm_io.py`); `agent/script.py` converts them, repairs missing
  icons/short texts deterministically, and estimates durations until TTS measures them.
- Fact-check gates (`agent/factcheck/`): numbers/units (en + ka number words), glossary names
  (`data/glossary/medical.json`), clause-level negation polarity. They override the LLM verdict.
- Fake mode (`APP_FAKE=1` or `--fake`): `agent/llm/fake_scenario.py` + `FakeRenderer`, separate
  ledger `metrics-fake.db`. Point `DATA_DIR` elsewhere to keep fake projects apart.

## Video contract (single source of truth: `agent/schemas/video_spec.py`)
- Change the Pydantic models, then run BOTH:
  `uv run python -m agent.schemas.export` (→ `video/src/generated/spec.schema.json`) and
  `npm run codegen -w video` (→ `video/src/generated/spec.ts` + `spec.zod.ts`). CI fails when stale.
- Never edit `video/src/generated/*`. `video/src/spec/types.ts` re-exports the generated types;
  composition props use `VideoProps` (zod-inferred alias — Remotion rejects interfaces as props).
- Remotion re-validates props with `VideoSpecSchema` in `calculateMetadata` (defence in depth).
- LLM structured output uses `agent.schemas.gemini.gemini_schema(model)` (inlines `$ref`, oneOf → anyOf,
  drops unsupported keywords). Avoid dict maps and tuples in LLM-facing models.
- Fixtures: `data/fixtures/specs/handwash-en.json` (valid, 50 s) + `invalid.json` (cases both sides reject).

## Templates (video/src/templates)
- 11 data-driven templates: title_card, step_card, do_dont, checklist, warning, timer, schedule,
  quiz_question, quiz_answer, summary, disclaimer. The LLM fills fields; it never chooses layout.
- Every text box is declared in `templates/boxes.ts` (width, max lines, size, weight). Templates draw
  text with `<FitLines>` (one block per wrapped line from `fitText()`), and `lib/checkSpec.ts`
  validates a spec with the SAME boxes — overflow is an error, never an ellipsis. Georgian glyphs are
  ~0.6 em wide (wider than Latin), so Georgian text needs ~15 % more room.
- Captions: `lib/captions.ts` chunks narration to the caption box and times chunks over the measured
  clip; the same cues drive the burned-in band and SRT/VTT.
- Motion is cheap only (fade/slide/scale/tick/ring in `templates/kit.tsx`). No particles or filters.
- Fixed UI words live in `UI_TEXT` (en/ka). Never `toUpperCase()` Georgian (Mtavruli is not bundled).
- Remotion composition ids allow only `[a-zA-Z0-9-]`: use `galleryId()`.
- Gallery (`examples/gallery.ts`): one example scene per template per language → compositions
  `Gallery-<template>-<lang>`, `Reel-<lang>`; snapshot baselines in `video/snapshots/`.

## Commands
| command | what |
|---|---|
| `uv run ruff check . ; uv run ruff format --check . ; uv run mypy ; uv run pytest` | Python checks |
| `npm run lint ; npm run format:check ; npm run typecheck ; npm test` | TS checks (all workspaces) |
| `uv run uvicorn agent.api.app:app --port 8000` + `npm run dev -w web` | API + UI (http://localhost:5173, token `?token=` or `APP_TOKEN`) |
| `uv run python -m agent.cli [--fake] create --source f --message "..." [--approve script,video]` | drive the agent from the CLI (`chat`, `resume`, `status`, `spend`) |
| `uv run python scripts/probe_models.py [--location eu]` | one call per model (availability) |
| `uv run python -m agent.evals.run [--live]` | mutation suite + metrics → `docs/evals/report.md` |
| `uv run pytest -m live --no-cov` | opt-in Vertex smoke tests (costs cents) |
| `npm run render:smoke -w video` | bundle + tiny render + ffprobe check |
| `npm run gallery -w video [-- --update]` | stills of every template (en+ka) → `out/gallery/contact-<lang>.png`; `--update` rewrites snapshots |
| `uv run python -m agent.schemas.export [--check]` + `npm run codegen -w video [-- --check]` | contract export + TS/zod codegen |
| `node node_modules/tsx/dist/cli.mjs video/scripts/render-worker.ts < req.json` | render worker (protocol: `docs/render-worker.md`) |
| `npm run bench -w video` | preview + final render of the ~57 s reel, prints fps / realtime / stages |
| `npm run test:stills -w video` | snapshot check (27x48 gray thumbnails, mean diff ≤ 6) |
| `npm run studio -w video` | Remotion Studio |
| `npm run fonts -w video` | copy Noto woff2 subsets to `video/public/fonts` + regenerate `src/catalog/fonts.json` / `font-metrics.json` |
| `npm run still -w video -- <id> [--props f.json] [--frame N]` | one PNG into `out/stills/` (e.g. `IconSheet`) |
| `npm run dev -w web` | web UI dev server |

## Rendering
- Presets: preview 540x960 @ 15 fps (`InstructionVideoPreview`, x264 ultrafast, no loudness pass),
  final 1080x1920 @ 30 fps (`InstructionVideo`, whole-mix loudness to -16 LUFS). Templates time
  everything in seconds via `useSec()`, so both frame rates render the same video.
- Outputs per render: `video.mp4` (always h264 + AAC, `enforceAudioTrack`), `video.srt`, `video.vtt`,
  `quiz.json`, `meta.json`. Bundle cached in `out/.bundle-cache/<hash>`.
- Spawn Node scripts as `process.execPath` + `node_modules/tsx/dist/cli.mjs` — `shell: true` or `.cmd`
  shims break on the space in the repo path. `npx tsx -e` hangs here; write a script file instead.

## Tooling gotchas
- Bash heredocs mangle `${}`, backticks and `\n`: write scripts with the editor tools instead.
- In `node -e` string replacements, `$'` / `$&` in the replacement are special (they once pasted a
  copy of the file into a function) — prefer the Edit tool.
- The Playwright MCP browser needs Chrome; the e2e test instead reuses Remotion's headless shell
  (`node_modules/.remotion/chrome-headless-shell`).
- Paths contain spaces: quote them; run ffmpeg with relative paths from the repo root.
- Remotion bundles copy `video/public/` into `%TEMP%`; `bundleProject()` deletes its bundle on exit.
