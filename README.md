# InstructVid

**Turn a source document into a fact-checked, narrated instructional video (30 seconds to 5 minutes) — by chatting.**

Upload an SOP, a safety procedure or a patient's discharge instructions, then say what you need:
*"a 45-second Georgian training video with one quiz"*. An agent plans the video, writes the
script, **proves every claim against your document**, translates it, narrates it with Gemini TTS
and renders a 1080×1920 video with burned-in captions and quiz checkpoints. You review the script
and the preview in a two-pane web app and steer everything in plain language
(*"make step 3 shorter and use the gloves icon"*).

| | |
|---|---|
| **Languages** | Georgian (`ka`) and English (`en`) — source and video can differ |
| **Output** | 1080×1920 H.264/AAC MP4 (30 fps), SRT + WebVTT captions, `quiz.json` |
| **Look** | Flat motion graphics ("airline-safety card" style), 11 data-driven scene templates, 148 pictograms |
| **Models** | Gemini on Vertex AI (Application Default Credentials — no API keys) |
| **Stack** | Python 3.12 · LangGraph · LangChain · FastAPI · Remotion 4 · React · Vite |

---

## Contents

- [Why](#why)
- [How it works](#how-it-works)
- [Fact-checking](#fact-checking)
- [Quick start](#quick-start)
- [Using it](#using-it)
- [Architecture](#architecture)
- [The video contract](#the-video-contract)
- [Scene templates](#scene-templates)
- [Rendering and speed](#rendering-and-speed)
- [Privacy and safety](#privacy-and-safety)
- [Configuration](#configuration)
- [Development](#development)
- [Project layout](#project-layout)
- [Project status](#project-status)
- [Licences](#licences)

---

## Why

Training and patient-education material lives in long documents nobody reads. Short videos work —
but a video that *invents* a step, a dose or a time is worse than no video. InstructVid is built
around one rule: **nothing reaches the screen unless the user's own source document supports it.**
Every scene stores the source chunks it relies on, every claim gets a verdict with a quote, and
numbers, units, names and negations are checked deterministically on top of the LLM.

Typical uses:

| Use case | Input | Output |
|---|---|---|
| Workplace safety / SOP training (kitchens, warehouses, factories) | SOP as PDF, DOCX, TXT or Markdown | Step-by-step procedure video with 1–2 quiz checkpoints |
| Patient education (clinics, hospitals) | Discharge instructions / procedure description | 45–60 s explainer in the patient's language, every claim traced to the source, disclaimer card |
| Customer / onboarding how-tos | Short how-to text | Same templates |

---

## How it works

```
upload ──► PII scrub ──► chunk + index (project-only RAG)
                                   │
chat ──► intake ──► plan ──► write script ──► fact-check every scene ──► fix (≤ 2 loops)
                                                     │
                                                     ▼
                                translate (+ back-translation gates)
                                                     │
                                         ┌───────────▼───────────┐
                                         │  YOU review the script │  approve · edit in chat · regenerate
                                         └───────────┬───────────┘
                                                     ▼
                       narrate (TTS + transcript check) ──► layout check ──► preview render
                                                                                   │
                                                                  ┌────────────────▼───────────────┐
                                                                  │   YOU review the preview video  │
                                                                  └────────────────┬───────────────┘
                                                                                   ▼
                                                               final render ──► ffprobe validation
```

The pipeline is a **LangGraph** state machine, one thread per project, checkpointed in SQLite —
kill the server mid-project and the conversation resumes where it stopped. The two review points
are real `interrupt()`s; your answer (approve / edit / regenerate) resumes the graph.

**Chat edits are typed patches, never free rewrites.** A message like *"make step 3 shorter and
use the gloves icon"* becomes `[regenerate_scene(step 3, "shorter"), set_icon(step 3, gloves)]`.
The ops are validated, applied deterministically, saved as a new version, and **only what changed
is recomputed**:

| Edit | Recompute |
|---|---|
| text / regenerate / add scene / add quiz | fact-check those scenes → TTS those scenes → render |
| language | translate → TTS all → render |
| voice | TTS all → render |
| icon / reorder / delete | render only |
| target duration | new script |

Narration clips are cached by `sha256(model | voice | language | text | prompt version)`, so
untouched scenes are cache hits — visible in the render panel.

---

## Fact-checking

For each scene (in parallel, via LangGraph `Send`):

1. **Claims** — Gemini Flash splits narration + on-screen text into atomic claims (instructions,
   numbers, prohibitions, the correct quiz answer).
2. **Evidence** — hybrid retrieval over *this project's* uploads only: BM25 + vector search
   (`gemini-embedding-2`, 768 dims), reciprocal-rank fusion, optional Flash rerank.
3. **Verdict** — Gemini Argon labels each claim `supported` / `partially_supported` /
   `unsupported` / `contradicts` and quotes the evidence span.
4. **Deterministic gates override the LLM:**
   - every **number, dose, unit, time and frequency** in a claim must appear in the evidence after
     normalisation — digits and number words in both languages (`20 seconds` = `ოცი წამი`,
     `3 times a day` = `დღეში სამჯერ`, `500 mg` = `500 მგ`);
   - **medication names and body parts** must appear in the source (glossary across ka/en + fuzzy
     match for drug-like words);
   - **negations keep their polarity** (`do not drive` must not become `drive`).
5. **Policy** — a final export is blocked until every claim (including quiz answers) is
   `supported`. Patient videos always end with a disclaimer card.

Translations are checked again: the script is fact-checked in the source language, translated,
back-translated by Flash, and the number/name/negation gates run on the result.

---

## Quick start

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | ≥ 0.8 | manages Python 3.12 and the `.venv` |
| Node.js | 22 | npm workspaces for `video/` and `web/` |
| ffmpeg + ffprobe | 7.x | used by absolute path from `FFMPEG_DIR` |
| Google Cloud SDK | any recent | for Application Default Credentials |
| A GCP project | — | Vertex AI API enabled |

### Install

```powershell
git clone <this repo> instructvid
cd instructvid

uv sync                 # creates .venv with a uv-managed CPython 3.12
npm install             # video/ + web/ workspaces (Remotion downloads its Chromium on first render)

gcloud auth application-default login
copy .env.example .env  # then set GOOGLE_CLOUD_PROJECT (and FFMPEG_DIR if needed)
```

Check that the models answer in your region (one tiny call each):

```powershell
uv run python scripts/probe_models.py
```

### Run the app

```powershell
uv run uvicorn agent.api.app:app --port 8000     # API
npm run dev -w web                               # UI on http://localhost:5173
```

No cloud account yet? Run everything with fake models, fake TTS and a fake renderer:

```powershell
$env:APP_FAKE = "1"; uv run uvicorn agent.api.app:app --port 8000
```

If a provider rate limit (429) stops a run, nothing is lost: press **Retry** in the chat
(or `POST /api/projects/<id>/retry`, or `agent.cli retry <id>`) and the run continues from its
last checkpoint.

### Or drive it from the command line

```powershell
uv run python -m agent.cli create `
  --source data/fixtures/sources/handwashing-sop-en.md `
  --message "A 45-second Georgian training video with one quiz" `
  --approve script,video

uv run python -m agent.cli chat <project-id> "make step 3 shorter and use the gloves icon"
uv run python -m agent.cli spend        # total recorded model spend
```

---

## Using it

**Left pane — chat.** Upload a `.pdf`, `.docx`, `.txt` or `.md` source (you see what was
redacted), then describe the video. Replies stream in; inline cards show the plan, the script, the
fact-check (failed claims show the source quote and *why*), translation checks and cost. Quick
replies cover the checkpoints: **Approve**, **Regenerate**, **Switch language**. Any free-text
message is an instruction: *"use Russian"* is refused (ka/en only), *"add a quiz about gloves"*,
*"slower voice"*, *"remove the warning"* are applied as typed edits.

**Right pane — video.** A 9:16 player with captions, a version selector (every edit creates a
version), a preview/final toggle, downloads (MP4, SRT, `quiz.json`) and an always-visible
**render-speed panel**: current stage, frames done/total, render fps, realtime factor, ETA, elapsed
time, per-stage timings (TTS, bundle, render, encode) and cache hits.

---

## Architecture

```
repo/
├── agent/    Python 3.12 — FastAPI + LangGraph + LangChain + google-genai (Vertex AI)
├── video/    Remotion 4 + React — scene templates, text fitting, render worker (TypeScript)
├── web/      Vite + React — two-pane chat + player UI
├── config/   models.yaml (the only place model names appear), app.yaml
├── data/     icon/glossary data, synthetic fixtures (runtime data is gitignored)
└── docs/     brief, ADRs, render-worker protocol
```

**Data flow:** chat message → FastAPI → LangGraph run (thread = project) → `VideoSpec` (Pydantic)
→ JSON → Remotion render worker (Node subprocess, JSON-lines progress) → MP4/SRT → SSE → UI.

### Models (`config/models.yaml`)

| Role | Model | Used for |
|---|---|---|
| intake, chat_edit, claim_extraction, back_translation, transcribe, rerank, pii_scrub | `gemini-3.8-flash` | fast structured work (falls back to Argon when rate-limited) |
| plan, write_script, fact_check_verdict, fix_script, translate | `gemini-4-argon` | reasoning, `thinking_level` LOW/MEDIUM |
| tts | `gemini-3.8-flash-tts` | narration, voice `Kore`, `ka-GE` / `en-US` |
| embeddings | `gemini-embedding-2` | 768-dim retrieval vectors |

All calls go through **one router** (`agent/llm/router.py`): roles from config, exponential backoff
with jitter on 429/5xx, a 429 fallback role with cooldown, an optional disk cache, per-call usage
and cost, a per-run spend cap and a global spend cap backed by a SQLite ledger. Structured output
uses Gemini JSON mode with flattened schemas and one validation retry.

### LangGraph

- **State** — messages (with cards), request, plan, spec, fact report, versions, render results,
  usage (custom reducer summing tokens/cost per role), status.
- **Nodes** — `intake`, `ingest_source`, `plan`, `write_script`, `fact_check` → `check_scene`×N →
  `fact_reduce`, `fix_script`, `translate`, `present_script`/`review_script`, `narrate`,
  `layout_check`, `render_preview`, `validate_video`, `present_video`/`review_video`,
  `render_final`, `done`, `chat_edit`, `apply_edit`. Each is a factory closing over injected
  dependencies — no globals.
- **Rules** — conditional edges contain routing only; fix loops are capped and exit early when the
  same failures repeat; every invocation sets a recursion limit; history is trimmed with
  `trim_messages` (the spec is the long-term memory).

---

## The video contract

The Pydantic models in [`agent/schemas/video_spec.py`](agent/schemas/video_spec.py) are the single
source of truth. JSON Schema is exported from them and TypeScript types + zod validators are
generated for the renderer:

```powershell
uv run python -m agent.schemas.export   # -> video/src/generated/spec.schema.json
npm run codegen -w video                # -> video/src/generated/spec.ts + spec.zod.ts
```

CI fails when the generated files are stale, and Remotion validates the props with zod again
before rendering. A hand-written example lives in
[`data/fixtures/specs/handwash-en.json`](data/fixtures/specs/handwash-en.json).

---

## Scene templates

The LLM fills fields; it never designs layouts. Every text box is declared once (width, max lines,
size, weight) and measured with the bundled fonts' real advance widths — the **same function** lays
out the text in the video and validates the script, so **overflow is an error, never an ellipsis**.

| Template | What it shows |
|---|---|
| `title_card` | title, subtitle, icon |
| `step_card` | step number, large pictogram, one instruction |
| `do_dont` | green ✓ panel vs red ✗ panel |
| `checklist` | items that tick in one by one |
| `warning` | hazard banner + icon |
| `timer` | animated ring, e.g. "scrub for 20 seconds" |
| `schedule` | times / days with a short instruction each |
| `quiz_question` | question, 2–4 options, countdown ring |
| `quiz_answer` | correct option highlighted + one-line explanation |
| `summary` | key points |
| `disclaimer` | patient videos: follow your doctor's instructions |

Fonts are Noto Sans + Noto Sans Georgian, bundled locally (no CDN). Icons come from a curated
148-entry catalog (Lucide + four custom pictograms: gloves, face mask, hand-wash, apron) with tags
in English and Georgian; unknown icon names fail validation. Motion is deliberately cheap — fades,
slides, scale pops, tick-ins and rings — so renders stay fast.

```powershell
npm run gallery -w video     # stills of every template in en + ka -> out/gallery/contact-*.png
```

---

## Rendering and speed

The render worker (`video/scripts/render-worker.ts`) reads one JSON request on stdin and prints
JSON-lines progress (`validate → bundle → render → encode → post`), then a `done` event with stage
timings, ffprobe checks and cache hits. The protocol is documented in
[`docs/render-worker.md`](docs/render-worker.md).

Measured on the dev laptop (i5-13450HX, 16 threads, 16 GB) with a 56.5 s video:

| Preset | Size | Frames | Wall time | Realtime |
|---|---|---|---|---|
| preview | 540×960 @ 15 fps | 848 | ~19 s | ×2.6 |
| final | 1080×1920 @ 30 fps | 1695 | ~48 s | ×1.2 |

---

## Privacy and safety

- **No personal data to the model.** Uploads are scrubbed before anything leaves the machine:
  deterministic patterns (names after labels, dates of birth, ID / record numbers, phones,
  addresses, e-mails) plus a Flash pass over the already-redacted text. The user sees what was
  redacted. Raw uploads stay local with a retention setting.
- **Uploaded text is data.** Lines that try to instruct the model are stripped, sources are wrapped
  in delimited blocks, and prompts tell the model never to follow instructions inside them.
- **Scope guard.** Requests outside instructional/explainer videos — and medical advice without a
  source document — are refused.
- **Human approval** is required before a final export; an audit log records who approved which
  version.
- **Auth to Google** is Application Default Credentials or a service account — never API keys.

---

## Configuration

`.env` (never committed — see [`.env.example`](.env.example)):

| Variable | Meaning |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | GCP project for Vertex AI |
| `GOOGLE_CLOUD_LOCATION` | `eu` (all models are available there) |
| `GOOGLE_GENAI_USE_VERTEXAI` | `True` |
| `FFMPEG_DIR` | folder containing `ffmpeg` / `ffprobe` |
| `APP_TOKEN` | bearer token the web app sends to the API |
| `MAX_RUN_COST_USD` | spend cap per graph run |
| `MAX_TOTAL_SPEND_USD` | spend cap across all runs (ledger in `data/metrics.db`) |
| `APP_FAKE` | `1` = fake models, TTS and renderer (no cost) |
| `REMOTION_LICENSE_KEY` | Remotion company licence, if you need one |

`config/app.yaml` holds speaking paces per language (Georgian ≈ 7.5 characters/s), duration limits,
loop caps and render presets.

---

## Development

```powershell
# Python
uv run ruff check . ; uv run ruff format --check . ; uv run mypy ; uv run pytest
uv run pytest -m live --no-cov          # opt-in smoke tests against real Vertex AI (costs cents)

# TypeScript (all workspaces)
npm run lint ; npm run format:check ; npm run typecheck ; npm test
npm run render:smoke -w video            # bundle + tiny render + ffprobe
npm run test:stills -w video             # template snapshot tests
npm run bench -w video                   # render speed numbers
```

Default test runs never call paid APIs: `FakeBackend` answers per role, TTS returns silent WAVs at
the measured pace, and `FakeRenderer` writes a tiny MP4 with ffmpeg.

---

## Project layout

```
agent/
  api/          FastAPI app, SSE streaming, uploads, downloads
  graph/        LangGraph state, nodes, wiring, runner (SQLite checkpointer)
  llm/          router, Vertex backend, usage ledger, disk cache, fakes
  rag/          loaders, hygiene, chunking, embeddings, Chroma store, hybrid retrieval
  factcheck/    claim checker, deterministic gates, number/unit normalisation (ka/en)
  tts/          narrator (cache, loudnorm, transcript check), WAV helpers
  render/       render-worker client, fake renderer, ffprobe validation
  privacy/      PII scrubber
  schemas/      VideoSpec contract, LLM I/O models, Gemini schema flattening
  prompts/      versioned prompt templates (*.md)
video/
  src/templates/  the 11 scene templates + text boxes
  src/lib/        textFit, captions, checkSpec
  scripts/        render worker, codegen, gallery/snapshots, bench
web/              Vite + React UI
config/           models.yaml, app.yaml
data/             glossary, fixtures (synthetic SOP + discharge instructions)
docs/             brief, ADRs, render-worker protocol
```

---

## Project status

| Area | State |
|---|---|
| Scene templates, text fitting, captions, icon catalog, fonts | ✅ done |
| Video contract (Pydantic → JSON Schema → TS/zod) | ✅ done |
| Render worker with progress, presets, validation | ✅ done |
| Model router (Vertex, retries, fallback, cost caps) | ✅ done |
| LangGraph pipeline, RAG, fact-check, translation, TTS, chat edits | ✅ done (end-to-end in fake mode and against Vertex AI) |
| Resilience: 429 fallbacks between Flash and Argon, resumable runs (Retry) | ✅ done |
| FastAPI + SSE | ✅ done |
| Web UI (two panes, cards, quick replies, render-speed panel) | ✅ done |
| Tests: Python 95 % coverage, video, web, Playwright smoke | ✅ done |
| Evals (mutation suite, metrics report), Dockerfile, deploy docs | ✅ done — see [docs/evals/report.md](docs/evals/report.md) |

---

## Licences

- Code: see the repository licence.
- **Remotion** is free for individuals and companies of up to 3 people; larger companies need a
  company licence — see [ADR 0002](docs/adr/0002-remotion-licence.md).
- Fonts: Noto Sans / Noto Sans Georgian, SIL Open Font License (`video/public/fonts/OFL.txt`).
- Icons: [Lucide](https://lucide.dev) (ISC) plus four custom pictograms in this repo.
