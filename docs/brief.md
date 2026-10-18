# Brief: chat-driven instructional video generator

> The single source of truth for the product. Keep it updated when decisions change.

---

## 0. How to work (read first)

1. **Plan before coding.** List the files to add, the dependencies (and why) and the phase order
   (§13). Record lasting decisions as ADRs in `docs/adr/`.
2. **Work phase by phase (§13).** Every phase ends green: lint, types, unit tests, plus one real
   render. Never leave the repo broken between commits.
3. **Ask instead of guessing** when a decision belongs to the product owner: licences of new asset
   packs and anything that costs money.
4. **Keep `CLAUDE.md` current.** Update its commands, conventions and gotchas whenever they
   change.

---

## 1. Product

**One-liner:** a user pastes or uploads a source document (an SOP, safety procedure, discharge
instructions, procedure description) and chats with an agent. The agent turns it into a
**30–60 s instructional video**: flat motion graphics, narration in Georgian or
English, burned-in captions and quiz checkpoints. A fact-check step proves that every scene is
supported by the source.

**Target users and use cases (MVP):**

| Use case | Input | Output |
|---|---|---|
| Workplace safety / SOP training (factories, warehouses, restaurants) | SOP text / PDF / DOCX | Step-by-step procedure video with 1–2 quiz checkpoints (question → countdown → answer) |
| Patient education (clinics, hospitals) | Discharge instructions / procedure description | 45–60 s explainer in the patient's language (ka / en); every claim is traced to the source |
| (stretch) Customer / onboarding how-tos | Short how-to text | Same template set |

**Non-goals:** medical advice beyond the source; generated photoreal imagery; long videos
(> 90 s); real patient data in prompts (§10).

---

## 2. UI: exactly two panes

Keep it minimal. There is no dashboard and no extra pages.

```
┌──────────────────────────────┬──────────────────────────────────────────┐
│  CHAT (left, ~40%)           │  VIDEO (right, ~60%)                      │
│                              │                                           │
│  agent + user messages       │  ┌──────────────┐  version: v3 ▾          │
│  (token streaming)           │  │  9:16 player │  ● preview  ○ final     │
│                              │  │  + captions  │                         │
│  inline cards:               │  └──────────────┘                         │
│   • plan / script summary    │  Render: frames 812/1800 · 41 fps          │
│   • fact-check results       │          1.4× realtime · ETA 0:24          │
│   • quick replies:           │  Stages: TTS 6.1s ✓  bundle 2.0s ✓          │
│     [Approve] [Shorten]      │          render 19.8s …  encode —          │
│     [Switch to English]      │  [Download MP4] [SRT] [quiz.json]          │
│  📎 upload source            │                                           │
│  [ message box … ] [Send]    │                                           │
└──────────────────────────────┴──────────────────────────────────────────┘
```

**Chat (left):**
- Messages stream token by token.
- Uploads: `.pdf`, `.docx`, `.txt` and `.md` sources.
- Inline cards for the plan, the script and the fact-check results. A failed claim shows its
  source quote and a "why" line.
- Quick-reply buttons for the human checkpoints: approve the script, approve the final video,
  regenerate, change language.
- Every free-text message is an instruction ("make scene 3 shorter", "use English",
  "add a quiz about gloves", "slower voice").

**Video (right):**
- Player with captions and a version selector (every edit creates a version).
- Preview / final toggle.
- **Render speed is always visible:**
  - current stage;
  - frames done / total;
  - render fps (frames per wall-clock second);
  - realtime factor (video seconds rendered per wall second);
  - ETA and elapsed time;
  - per-stage timings: TTS, bundle, render, encode;
  - cache hits.
- Downloads: MP4, SRT and `quiz.json`.

**Tech:** Vite + React + TypeScript; SSE from the backend; no state library needed (use a
`useReducer` over server events). Use mobile-friendly breakpoints, but desktop first.

---

## 3. Visual style: "instruction video", fast to render

Use **flat vector motion graphics**, the look of airline-safety or
onboarding videos:

- **Scene templates** (React components in Remotion, data-driven, no free-form layout by the
  LLM):
  - `TitleCard`;
  - `StepCard` (step number, pictogram, 1–2 short lines);
  - `DoDont` (green ✓ vs red ✗ panels);
  - `Checklist` (items tick in one by one);
  - `Warning` (hazard banner + icon);
  - `Timer` (e.g. "wash hands 20 s", animated ring);
  - `Dosage/Schedule` (table/timeline);
  - `QuizQuestion` (question + 2–4 options + countdown);
  - `QuizAnswer` (correct option highlighted + 1-line explanation);
  - `Summary`;
  - `Disclaimer` (patient videos).
- **Assets:** a bundled, licence-clean pictogram set (e.g. Tabler Icons or Lucide, MIT). The
  LLM picks icons **only by name from a catalog** (`src/catalog/icons.json`, with tags in
  en/ka). An unknown icon fails validation. No image generation.
- **Motion:** simple, cheap transitions only (fade, slide, scale, highlight ring, arrow
  pointer, tick-in). No particles, no per-pixel effects, no shaders.
- **Typography:** large captions that are safe for Georgian and Latin. Use Noto Sans and
  Noto Sans Georgian, bundled locally rather than from a CDN.
  - **Text fitting:** a deterministic function measures every text box. Overflow is a
    validation error, not a CSS ellipsis.
- **Brand theme:** one theme object (colours, font sizes, safe areas) plus per-tenant overrides.
- **Format:** 1080×1920 (9:16), **30 fps** for final renders. Previews are 540×960 at 30 fps
  (or 15 fps); a 16:9 variant is optional later.
- **Performance target:** a 60 s final video renders in **≤ 60 s** on the dev laptop, and a
  preview in ≤ 20 s. Measure it and show it in the UI.

---

## 4. Architecture

Use a monorepo with three parts: the Remotion project, the agent backend and the web UI.

```
repo/
├── video/          # Remotion project: templates, render worker (TS)
├── agent/          # Python 3.12 (uv): FastAPI + LangGraph + LangChain + Gemini (Vertex)
├── web/            # Vite + React chat + player UI
├── config/models.yaml
├── data/           # icon catalog, glossaries, sample sources, eval fixtures
└── docs/           # audit, ADRs, deploy
```

**Data flow:** chat message → FastAPI → LangGraph run (thread = project) → `VideoSpec`
(Pydantic) → JSON → Remotion render worker (Node, subprocess, JSON-lines progress) →
MP4/SRT → SSE progress → UI.

**Single source of truth for the video contract:** the Pydantic models in `agent/`.
- Export JSON Schema with `uv run python -m agent.schemas.export`.
- Generate TS types and zod validators for `video/` from it (e.g. `json-schema-to-typescript`
  + zod).
- CI fails if the generated files are stale.
- Remotion validates the incoming props with zod again: defence in depth.

**Render worker** (`video/scripts/render-worker.ts`):
- reads a JSON request on stdin;
- runs `bundle()` once (cached) → `selectComposition()` → `renderMedia()` with `onProgress`;
- prints JSON lines: `{stage, renderedFrames, encodedFrames, totalFrames, elapsedMs}`, then
  `{done, mp4, durationMs}`;
- has a hard timeout. Concurrency comes from config (default `os.cpus().length - 1`).
  ffmpeg handles post-processing (loudness, faststart).

---

## 5. LangGraph design: do it properly

**State** (`TypedDict` or Pydantic, JSON-serialisable for the checkpointer):
- `messages: Annotated[list, add_messages]` holds the chat;
- `source` (doc ids);
- `spec` (VideoSpec);
- `fact_report`;
- `versions: Annotated[list, operator.add]`;
- `render`;
- `usage` (custom reducer summing tokens/cost per model);
- `status`.

**Nodes** (one module each, factories closing over injected deps, with no globals):

| Node | Type | Job |
|---|---|---|
| `intake` | rules + Flash | language detection, scope/safety screen, PII screen (§10) |
| `ingest_source` | deterministic + embeddings | parse, chunk and index the uploaded source (§6) |
| `plan` | Argon, structured | audience, goal, target duration, outline of steps, quiz plan |
| `write_script` | Argon, structured | `VideoSpec` scenes: template, icon, on-screen text, narration, source chunk ids |
| `fact_check` | map-reduce subgraph (`Send` per scene) | claims → evidence (RAG on the source only) → verdict (§7) |
| `fix_script` | Argon | rewrites only the failing scenes using the verdicts (max 2 loops, then escalate) |
| `translate` | Argon + glossary | target language; back-translation + numbers check |
| `review_script` | `interrupt()` | the user approves or edits in chat |
| `narrate` | TTS | per scene, cached, measured durations (§8) |
| `layout_check` | deterministic | text fit, timing plan, icon catalog, durations 30–60 s |
| `render_preview` / `render_final` | worker subprocess | progress via `get_stream_writer()` custom events |
| `validate_video` | deterministic | ffprobe, duration, captions present, narration matches spec (§9) |
| `review_video` | `interrupt()` | approve / request change |
| `chat_edit` | Flash → `EditPlan` | turns a chat instruction into typed patch ops (§5.1) |
| `apply_edit` | deterministic | applies the ops, bumps the version, routes to the minimal recompute |

**Rules:**
- **Routing:** conditional edges hold only routing logic; no business logic in edges.
- **Loop guards:** fix loops have caps plus early exit when the same failure repeats.
- **Spend cap:** `max_run_cost_usd`.
- **Checkpointing:** `SqliteSaver` (`langgraph-checkpoint-sqlite`), with `thread_id` =
  project id. Resuming after a server restart must work, and a test covers it.
- **HITL:** use `interrupt()` + `Command(resume=…)`. One interrupt payload has a `kind` field
  (`script` | `video`), so the UI renders the right quick replies.
- **Streaming:** `graph.stream(..., stream_mode=["messages", "updates", "custom"])`. Use
  `messages` for token streaming to the chat, `updates` for cards, and `custom` for render
  progress.
- **Memory:** trim and summarise chat history over a token budget
  (`langchain_core.messages.trim_messages`). The spec in state is the long-term memory, not
  the chat.
- **Recursion limit:** set it on every invocation.

### 5.1 Chat editing = typed patches, never free rewriting

`chat_edit` returns `EditPlan { ops: list[EditOp], reply: str }`.

`EditOp` is a discriminated union:
- `set_text(scene, field, value)`;
- `set_icon`;
- `reorder`;
- `delete_scene`;
- `add_scene(template, after)`;
- `set_language`;
- `set_voice`;
- `set_target_duration`;
- `add_quiz`;
- `regenerate_scene(scene, instruction)`.

`apply_edit` validates the ops against the schema and the catalog, applies them
deterministically and records a version, then reruns **only what changed**:
- a text edit → fact-check that scene → TTS that scene → re-render;
- a language change → translate → TTS all → re-render;
- an icon change → re-render only.

Unsupported or unsafe requests get a chat reply, not silent changes.

### 5.2 LangChain: use it where it adds value

- **Use:** `langchain-core` messages and `Document`; `langchain-text-splitters`; document
  loaders (`PyPDFLoader` / `pypdf`, `Docx2txtLoader` or `python-docx`); the retriever
  interface (`BaseRetriever`) so retrieval is swappable and testable; `langchain-chroma` for
  the vector store; BM25 via `langchain-community` `BM25Retriever` + an `EnsembleRetriever` for
  hybrid search.
- **Model calls** go through **one router** (`agent/llm/router.py`): roles from
  `config/models.yaml`, retries with backoff + jitter on 429/5xx, a disk cache in dev/tests,
  usage/cost tracking and structured output parsed into Pydantic with one validation retry.
  - Use the `google-genai` SDK on Vertex directly, or `langchain-google-vertexai` (`ChatVertexAI`)
    if you prefer LangChain chat models.
  - **Pick one and use it everywhere.** Never put a model name in code.
- **Avoid** "agent executor" magic; LangGraph is the orchestrator.

---

## 6. RAG done right (source-grounded, per project)

- **Scope:** retrieval for scripting and fact-checking uses **only the user's uploaded
  source(s)** for that project, never the open web.
  - A shared, curated knowledge base (glossaries, house style, template docs) lives in separate
    collections.
- **Ingestion:** parse → normalise → split by headings / numbered steps first, then
  `RecursiveCharacterTextSplitter` at about 300–500 tokens with ~15 % overlap.
  - **Keep metadata:** `project_id`, `doc_id`, `page`, `section`, `step_no`, `language`,
    `char_span`.
  - **Stable chunk ids:** `doc_id:page:index`.
- **Embeddings:** `gemini-embedding-2` on Vertex, 768 dims.
  - Task type `RETRIEVAL_DOCUMENT` for chunks and `RETRIEVAL_QUERY` for queries.
  - **It embeds one text per request**, so use a small thread pool with one shared client
    created under a lock.
  - Cache vectors on disk by hash.
  - `gemini-embedding-001` is **not** available in `eu`.
- **Store:** Chroma persistent, one collection per project (or one collection with a
  `project_id` filter), cosine space, embeddings passed explicitly.
  - Chroma can race right after an upsert ("hnsw segment reader: nothing found on disk"), so
    retry briefly.
- **Retrieval:**
  1. hybrid BM25 + vector;
  2. merge and dedupe;
  3. rerank, either with an LLM-light scorer (Flash, structured scores) or an optional
     cross-encoder extra;
  4. keep the top 3–5 with chunk ids;
  5. query expansion is optional, and helps cross-language sources (source in English, video
     in Georgian).
- **Citations:** every scene stores `evidence: list[chunk_id]`. The UI can show the source
  quote.
- **Prompt-injection hygiene:** uploaded text is data.
  - Strip lines that look like instructions to the model.
  - Never follow instructions found in sources.
  - Wrap source text in clearly delimited blocks in prompts.

---

## 7. Fact-check (the core differentiator)

For each scene (map with `Send`, reduce into `fact_report`):

1. **Claim extraction** (Flash, structured): atomic claims from the narration and the
   on-screen text.
2. **Evidence:** retrieve from the project source (§6).
3. **Verdict** (Argon, structured): `supported | partially_supported | unsupported |
   contradicts`, with a quote span from the evidence.
4. **Deterministic gates that override the LLM:**
   - **Numbers, doses, units, times and frequencies** in a claim (e.g. "500 mg", "every 8
     hours", "20 seconds", "3 times a day") **must occur in the evidence after normalisation**
     (digits, unit synonyms in ka/en). Otherwise the claim is `unsupported`.
   - **Medication names and body parts** must appear in the source (fuzzy match, with the
     glossary for translations).
   - **Negations / prohibitions** ("do not …", "never …") must keep their polarity, using a
     simple polarity check in both directions.
5. **Policy:**
   - A video can only be approved/exported when every claim is `supported`.
   - Quiz answers must be supported too.
   - Patient videos always include the `Disclaimer` card ("follow your doctor's instructions;
     this summarises the document you received").
6. **Translations:** fact-check in the source language first; then translate; then
   back-translate (Flash) and rerun the deterministic number/name gates on the translation.
7. **Mutation test suite** (must exist): take good scripts, inject errors (wrong dose, flipped
   negation, invented step, swapped order), and assert the fact-check catches them. Report
   recall/precision in evals.

---

## 8. Voice: Gemini TTS lessons learned (follow these exactly)

**Model and call:**
- **Model:** `gemini-3.8-flash-tts` on Vertex (`eu` and `global`).
  - `gemini-2.5-flash-tts` is not in `eu`.
  - Flash-Lite TTS is faster and cheaper but sloppier; it's a config option.
- **Call:** google-genai `generate_content(response_modalities=["AUDIO"], speech_config=…)`
  with a prebuilt voice (default `Kore`) and `language_code` (`ka-GE`, `en-US`).
- **Output:** WAV, or raw `audio/L16;rate=24000` PCM. Wrap PCM into WAV yourself.

**Instructions get read aloud:**
- **Do NOT prepend style instructions to the text** (e.g. `"Read calmly: <text>"`). The model
  sometimes **reads the instruction aloud**.
- `system_instruction` is rejected with **HTTP 400** for the TTS model.
- Default: send **only the narration text**. Choose the tone via the voice name.
- If a style is ever needed, test it, and keep the transcript check below enabled.

**Transcript verification (mandatory):**
- After synthesising a clip, transcribe it with `gemini-3.8-flash` (audio input, "transcribe
  verbatim").
- Compare it with the narration: normalised character similarity ≥ 0.85, plus every number
  present.
- On mismatch, retry once; then fail the scene with a clear message.
- This catches spoken instructions, skipped words and hallucinated additions.

**Clips, cache and timing:**
- **Loudness:** normalise with ffmpeg `loudnorm=I=-16:TP=-1.5`, mono 24 kHz.
- **Cache:** cache clips by `sha256(model|voice|language|text|tts_prompt_version)`. **Bump
  `tts_prompt_version` whenever the request format changes**, or stale bad audio comes back
  from the cache.
- **Pace:** measured Georgian pace for Flash TTS is about **7.5 characters/s** (calm). Put the
  pace in settings per language and measure en with a script.
  - The script writer gets a character budget: a 60 s Georgian video holds about 400 narration
    characters in total.
  - **Timing comes from measured clip durations**, never from estimates.
- **Listening check:** `scripts/check_tts.py` renders sample sentences per language, model and
  voice. Ask the user to listen before changing the default voice.
- **Quota:** TTS quota is low per minute, so expect 429s. The router's backoff must cover TTS
  calls, and per-scene clips are generated sequentially or with low concurrency.

---

## 9. Video validation (deterministic)

- **ffprobe:**
  - H.264 + AAC;
  - 1080×1920 at 30 fps (final);
  - duration within **30–60 s** (configurable; a hard cap of 90 s);
  - file length = planned length ± 0.3 s.
- **Timing:** each narration clip fits its scene, and quiz countdowns respect the minimum
  reading time.
- **Text:**
  - every text box passes the fit check (the same function the templates use);
  - the font has glyphs for all characters, or the render fails;
  - captions (SRT) exist and are in sync.
- **Content:**
  - the narration audio transcript matches the spec (§8);
  - every number spoken or shown is in the fact-checked spec;
  - every icon exists in the catalog.
- **Optional:** sample 3 frames for a Flash "is anything unreadable or clipped?" advisory.

---

## 10. Privacy, safety, compliance

- **No PHI or personal data to the LLM:**
  - Run a deterministic + Flash PII scrubber on uploads (names, dates of birth, IDs, phone
    numbers, addresses, MRNs) **before** anything leaves the machine.
  - Show the user what was redacted.
  - Store raw uploads locally only, with a retention setting.
- **Scope guard:** refuse requests to create medical advice without a source document, and
  anything outside instructional/explainer videos.
- **Human approval** is required before a final export; the audit log stores who approved
  which version.
- **Remotion licence:** free for individuals and companies of up to 3 people. If the business
  grows, clinics and factories are commercial customers, so note the licence in the README and
  in `docs/adr`.
- **Auth:** Vertex AI via **Application Default Credentials / service account**, never API
  keys. Read the project/location from `.env` (`GOOGLE_CLOUD_PROJECT`,
  `GOOGLE_CLOUD_LOCATION=eu`, `GOOGLE_GENAI_USE_VERTEXAI=True`). Never commit `.env` or
  credentials.

---

## 11. Models and config

`config/models.yaml` is the only place model names appear:

| Role | Model | Notes |
|---|---|---|
| intake, chat_edit, claim_extraction, back_translation, transcribe, rerank | `gemini-3.8-flash` | temperature 0–0.3 |
| plan, write_script, fact_check_verdict, fix_script, translate | `gemini-4-argon` | `thinking_level` LOW/MEDIUM; **`MINIMAL` and `thinking_budget` are rejected with 400** |
| tts | `gemini-3.8-flash-tts` | voice `Kore`, `language_code` per video |
| embeddings | `gemini-embedding-2` | 768 dims, one text per request |

**Behaviour and cost:**
- Argon latency is 10–70 s per call, so stream progress and show it.
- Pricing (Vertex intro): Argon $2/$10 per 1M tokens in/out; Flash $0.75/$3.75; Flash TTS
  $0.50 in / $9 audio-out per 1M (~25 audio tokens/s); embeddings $0.20.
- Track usage per role and show the cost per video in chat.
- Use Gemini-friendly JSON schemas: flatten `$defs`, avoid `dict[str, X]` maps and tuples,
  prefer lists of objects and explicit fields.

---

## 12. Code quality and testing

**Python (`agent/`):**
- uv (Python 3.12, `UV_PYTHON_PREFERENCE=only-managed` on this machine; the system 3.12 is
  broken);
- ruff (lint + format) and mypy `--strict`;
- pytest, pytest-asyncio, pytest-cov, with **≥ 85 % coverage** of `agent/`;
- structlog with `thread_id` on every log line, and no `print`;
- prompts in `agent/prompts/*.md` with a `<!-- prompt: name | version: N -->` header, never
  inline.

**TypeScript (`video/`, `web/`):** `tsc --strict`, eslint, prettier, vitest, plus Testing
Library for the UI.

**Required tests (no real API calls in default test runs; use the marker `live` for opt-in
smoke tests):**
- **Schemas:** valid/invalid fixtures; the JSON Schema export matches the generated TS (CI check).
- **Fakes:** `FakeLLM` (responses keyed by role: value / list / callable), `FakeTTS` (silent
  WAV at the measured pace), `FakeRenderer` (writes a tiny MP4 with ffmpeg `testsrc` + `sine`).
- **Graph:**
  - routing and fix-loop caps;
  - an early exit on a repeated failure;
  - the spend cap;
  - HITL interrupt/resume;
  - **resume after a "restart"** (a new graph over the same SQLite file);
  - chat edits causing a minimal recompute (assert which nodes ran).
- **RAG:**
  - chunking metadata and ids;
  - hybrid retrieval with a deterministic hash embedder;
  - project isolation (project A never retrieves project B);
  - injection lines stripped.
- **Fact-check:**
  - the deterministic gates (numbers/units in ka/en, negation polarity);
  - the **mutation suite** (§7).
- **TTS:** PCM → WAV, cache-key versioning, the transcript-similarity gate, 429 retry.
- **Render:**
  - the worker protocol with a fake;
  - one real small render (preview size, 2–3 scenes) checked with ffprobe;
  - template text-fit unit tests;
  - `renderStill` snapshots of each template (hash or a pixel-diff tolerance).
- **API:**
  - httpx `TestClient`;
  - SSE event order (`token`, `card`, `render_progress`, `awaiting_review`, `done`);
  - uploads;
  - auth;
  - downloads.
- **Web:**
  - the event reducer;
  - the chat quick replies;
  - the render-speed panel maths (fps, realtime factor, ETA);
  - one Playwright smoke test of the built UI against the API with fakes.

**CI (GitHub Actions):**
- jobs `agent` (uv, ruff, mypy, pytest with ffmpeg + Chromium installed), `video` (tsc,
  eslint, vitest, one tiny render), `web` (tsc, vitest, build);
- `evals-smoke` is a manual workflow only, because it costs money.

---

## 13. Phases (each ends green with one real render)

| Phase | Content | Done when |
|---|---|---|
| P0 Plan | approved plan, ADRs | owner approves |
| P1 Scaffold | monorepo layout, uv project, Remotion project, CI skeleton | checks green, layout in place |
| P2 Templates | instruction-style templates, theme, icon catalog, text-fit function, stills + vitest | stills of every template look right; text fit tested |
| P3 Contract and render worker | Pydantic `VideoSpec` → JSON Schema → TS/zod codegen; render worker with JSON-lines progress; preview/final presets | a hand-written spec renders; speed measured |
| P4 Agent core | router (Vertex/ADC), plan + script nodes, LangGraph state, checkpointer, CLI `create` | source → spec → preview video from the CLI |
| P5 RAG + fact-check | ingestion, hybrid retrieval, claim/verdict subgraph, deterministic gates, mutation suite | mutation recall ≥ 0.9 on fixtures |
| P6 Voice + languages | TTS (§8 rules), transcript check, translation + back-translation, ka/en pace | narrated ka/en videos pass validation |
| P7 Chat editing + HITL | `chat_edit` / `apply_edit`, versions, minimal recompute, interrupts | edits via chat re-render only what changed |
| P8 API + UI | FastAPI + SSE, two-pane React UI with the render-speed panel | the full flow works in the browser |
| P9 Evals, observability, packaging | benchmark (synthetic SOPs + discharge texts, ka/en), metrics, `metrics.db`, Dockerfile, docs | eval report committed; README updated |

**Eval metrics:**
- fact-check recall/precision on injected errors;
- the share of scenes supported on the first pass;
- the duration-in-range rate;
- the transcript match rate;
- render time p50/p90 and the realtime factor;
- cost per video;
- a one-shot baseline (a single LLM prompt → script, with no fact-check), scored by the same
  validators.

---

## 14. Environment gotchas on this machine (Windows 11)

- `uv` is in `%USERPROFILE%\.local\bin`; set `UV_PYTHON_PREFERENCE=only-managed`, because the
  system Python 3.12 at `AppData\Local\Programs\Python\Python312` is broken (no `subprocess`
  module).
- The console is cp1252: call `sys.stdout.reconfigure(encoding="utf-8")` in CLIs, or Georgian
  output crashes.
- ffmpeg/ffprobe 7.1.1 are installed (gyan.dev build). The repo reads `FFMPEG_DIR` from
  `.env`.
- Bash heredocs that contain Python with `\n` escapes get mangled by the tool layer; write
  files with the editor tools instead.
- Playwright Chromium is installed for Python; the Node side needs its own Remotion browser
  download (Remotion handles it).
- Vertex location `eu` works for every model listed in §11. Check model availability with a
  1-call probe script before switching locations.

---

## 15. Definition of done

1. **Workplace safety:** uploading a restaurant hand-washing SOP (English) and asking in chat
   for "a 45-second Georgian training video with one quiz" produces a fact-checked,
   Georgian-narrated 1080×1920 MP4 with captions and a working quiz checkpoint. All validation
   is green and the render speed shows in the UI.
2. **Patient education:** uploading discharge instructions (synthetic, no real patient data)
   and asking for "a Georgian explainer" produces a 45–60 s video in which **every** claim is
   `supported` with a visible source quote, plus the disclaimer card. An injected wrong dose is
   caught and fixed before approval.
3. **Chat editing:** "make step 3 shorter and use the gloves icon" creates version v2 and
   re-renders without redoing TTS for untouched scenes (proven by cache hits in the speed
   panel).
4. **Recovery:** killing and restarting the server mid-project resumes the same thread.
5. **Quality:** all checks green, coverage ≥ 85 %, eval report committed and README/CLAUDE.md
   updated.
