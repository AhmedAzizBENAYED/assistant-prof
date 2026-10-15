# Architecture decisions

Each entry records a decision, why it was taken and what it costs. To change a decision, add a new entry that supersedes it; never edit an accepted entry except to mark it superseded.

Format: **ADR-NNN, Title** · Status · Date

---

### ADR-001, Local desktop application for Windows
Accepted · 2026-10-15
- **Decision:** the product runs entirely on the teacher's Windows laptop; only AI and speech-to-text calls go to the internet.
- **Why:** no server cost, documents stay on the machine, works offline for non-AI features.
- **Cost:** we must handle installation, updates and diverse hardware ourselves.

### ADR-002, Tauri 2 for the desktop shell
Accepted · 2026-10-15
- **Decision:** native window via Tauri 2 (WebView2), not Electron, not a browser tab.
- **Why:** small footprint for low-end laptops; "real app" feel; WebView2 is present on Windows 10/11 and the installer can bootstrap it.
- **Cost:** Rust toolchain for developers; a sidecar process to manage.

### ADR-003, React + Vite + TypeScript frontend
Accepted · 2026-10-15
- **Why:** known by the team, mature ecosystem, works inside Tauri.

### ADR-004, Python backend as a sidecar
Accepted · 2026-10-15
- **Decision:** FastAPI backend packaged with PyInstaller (onedir) and started by Tauri on 127.0.0.1 with a random port and session token.
- **Why:** the best .docx (python-docx/lxml) and agent (LangGraph) libraries are in Python.
- **Cost:** packaging size, antivirus false-positive risk (mitigated: onedir, no UPX).

### ADR-005, The AI proposes operations; code applies them
Accepted · 2026-10-15
- **Decision:** models never write files or XML. They return operations from a closed, validated catalogue; a deterministic executor applies them on a copy; the teacher approves before a new version is created.
- **Why:** reliability, testability, safety against prompt injection, no corrupted documents.

### ADR-006, The original file is never modified
Accepted · 2026-10-15
- **Decision:** imported files are copied into a workspace; every change creates a new version; export writes a copy; overwriting the original requires an explicit confirmation.

### ADR-007, docx-preview for the page view
Accepted · 2026-10-15
- **Decision:** render documents in the frontend with `docx-preview`; LibreOffice is not a dependency.
- **Cost:** less faithful than a PDF render; block mapping must be validated (spike T-600, fallback editing view).

### ADR-008, Strictly free AI providers, no local LLM
Accepted · 2026-10-15
- **Decision:** Gemini, Groq and Mistral free tiers as main providers, OpenRouter `:free` as last resort; no paid credits; no Ollama.
- **Why:** 0 $ budget; target laptops are too weak for local models; documents are not confidential.
- **Cost:** limited and changing quotas → multi-provider fallback, quota tracking, clear degradation, call-budget discipline. Free tiers may use requests for training; disclosed in the setup screen.

### ADR-009, Fallback chains per task, configured outside code
Superseded by ADR-026 · 2026-10-15
- **Decision:** ordered model chains per task (`route`, `plan`, `write_fr`, `classify`, `stt`) in YAML; no model name in code.
- **Why:** free models change without notice; updates must not require a release.

### ADR-010, Rule-based fast path before any AI call
Accepted · 2026-10-15
- **Decision:** frequent unambiguous formatting commands are handled by French rules without calling a model.
- **Why:** saves free quota, instant response.

### ADR-011, Template learning from teachers' own documents
Accepted · 2026-10-15
- **Decision:** templates are learned from any teacher document: container extraction (styles, numbering, sections, header/footer), role classification (rules + at most one LLM call), mandatory teacher review, profile with exemplars and conventions. Built-in templates use the same pipeline.
- **Why:** the product must work for any teacher and any document.

### ADR-012, Exemplar cloning to format generated content
Accepted · 2026-10-15
- **Decision:** generated content is role-tagged; the renderer clones a real paragraph from the teacher's document for each role and replaces its text.
- **Why:** reproduces the teacher's exact formatting instead of approximating it.

### ADR-013, Stable block IDs from `w14:paraId`
Superseded by ADR-022 · 2026-10-15
- **Decision:** block IDs come from Word's paragraph IDs; missing ones are generated and written into the working copy.
- **Why:** IDs survive save/reload, undo/redo and versions, so operations and UI selections stay valid.

### ADR-014, Voice: Groq Whisper first, local STT optional and off by default
Superseded by ADR-030 · 2026-10-15
- **Why:** free and accurate in French; target hardware unknown and possibly weak.

### ADR-015, Thin in-house LLM gateway instead of LiteLLM
Accepted · 2026-10-15 · supersedes the LiteLLM suggestion made during early discussion
- **Decision:** a small gateway over the providers' OpenAI-compatible chat endpoints (`httpx`), with our own router, quota tracker and structured-output layer.
- **Why:** all four providers expose OpenAI-compatible endpoints; we need custom quota and cooldown logic anyway; fewer transitive dependencies and a smaller PyInstaller bundle; full control and testability.
- **Cost:** we maintain provider quirks ourselves (documented in `PROVIDERS.md`, covered by contract tests with recorded responses).

### ADR-016, API keys in Windows Credential Manager
Accepted · 2026-10-15
- **Decision:** `keyring` stores keys; never in files, environment dumps or logs.

### ADR-017, Unsigned installer
Accepted · 2026-10-15
- **Decision:** no code-signing certificate (0 $). The user guide explains the SmartScreen warning. Tauri updater signatures (free key pair) still protect updates.

### ADR-018, Human approval before any document change
Accepted · 2026-10-15
- **Decision:** every AI change is a proposal with a diff; nothing is applied without the teacher's click. Outlines for new documents are approved before content is written.

### ADR-019, SQLite for local state
Superseded by ADR-028 · 2026-10-15
- **Decision:** one SQLite database (SQLAlchemy 2 + Alembic) for history, conversations, templates index, quota counters, settings; LangGraph checkpoints in SQLite too.

### ADR-020, Synthetic corpus until real documents exist
Accepted · 2026-10-15
- **Decision:** no real teacher documents are available; a generator builds a diverse synthetic corpus (styled, hand-formatted, table layouts, logos, bilingual headers, text boxes, tracked changes…). Real documents are added when available and become the reference.
- **Cost:** risk of surprises on real documents; mitigated by deliberately messy fixtures and the review step.

---

*ADR-021 to ADR-035 record the design review of 2026-10-15 (architecture v1.1).*

### ADR-021, Inline markup with marks, opaque tokens and style spans
Accepted · 2026-10-15
- **Decision:** the rewrite markup has five marks: `**gras**`, `*italique*`, `__souligné__`, `^^exposant^^`, `,,indice,,`. Non-text run content (hyperlinks, footnote/endnote references, tabs, breaks, bookmarks, fields contained in the paragraph) becomes opaque tokens `⟦n⟧` whose XML the executor restores verbatim. Any other formatting difference not covered by marks (colour, highlight, font, size) becomes numbered style spans `⟦sN⟧…⟦/sN⟧` referring to the original run properties. The validator rejects a rewrite unless every token appears exactly once (order may change) and every style span is balanced and refers to an existing span id. Fields that span several paragraphs (e.g. a table of contents) still lock their paragraphs.
- **Why:** with four marks only, a rewrite silently dropped links, note references, tabs, breaks, colours and subscripts (common in science documents).
- **Cost:** a more complex parser, serializer and validator; the model must copy tokens faithfully (invalid answers go through the repair retry).

### ADR-022, Block IDs: deterministic generation, duplicate repair, namespaces
Accepted · 2026-10-15 · supersedes ADR-013
- **Decision:** block IDs come from `w14:paraId`. On import, every part holding paragraphs is checked; missing and duplicated IDs (the first occurrence keeps its ID) are replaced by IDs derived from a hash of the part name and the paragraph position (8 hex digits, `00000001`–`7FFFFFFF`, re-hashed with a counter on collision, unique across all parts); `w14:textId` likewise. Missing `w14`/`mc` namespace declarations and the `mc:Ignorable` entry are added. Every paragraph created by the executor or the renderer gets fresh IDs, never the exemplar's. IDs are written on the working copy only.
- **Why:** IDs must survive save/reload, undo/redo and versions; cloned exemplars would otherwise duplicate IDs; real files contain duplicates; files without the namespace declarations would trigger Word's "unreadable content" error; deterministic IDs keep fixtures and golden tests stable.
- **Cost:** an import-time pass over all parts.

### ADR-023, Rules-only role classification on every imported document
Accepted · 2026-10-15
- **Decision:** every imported document (not only templates) is classified by the rule-based classifier with zero AI calls; the role map is cached per version and returned by `GET /documents/{id}`. The batched LLM pass for low-confidence blocks runs only when explicitly requested.
- **Why:** the fast path, target resolution and role-based insertion need roles on the document being edited; spending quota on every import is not acceptable.
- **Cost:** lower role accuracy on messy documents until the teacher asks for the LLM pass.

### ADR-024, Instruction runs with a resumable event stream
Accepted · 2026-10-15
- **Decision:** `POST /conversations/{id}/instructions` returns a `run_id`; events are read from `GET /runs/{id}/events` (SSE with event ids, replay from `Last-Event-ID`) using `fetch` streaming. Resuming a run after accept/reject/approve emits on the same stream. A disconnect never cancels a run; `POST /runs/{id}/cancel` does. On backend startup, every run still marked running (including while streaming) is set to `interrupted`; the UI shows "La dernière demande a été interrompue." with a "Relancer" button, and an interrupted run never blocks a new run on the same document. Runs awaiting a decision survive restarts through the checkpointer.
- **Why:** `EventSource` cannot send the `X-Session-Token` header nor POST; reconnecting a POST stream would resend the instruction; events produced after a resume need a stream; a crash or power cut must not leave a document locked by a run that will never finish.
- **Cost:** the backend keeps each run's events and statuses; a custom streaming client in the frontend; work in progress at crash time is lost and must be relaunched.

### ADR-025, Proposals bound to their base version; one active run per document
Accepted · 2026-10-15
- **Decision:** proposals and outlines record `base_version_id`. Accepting or approving when the document head has moved returns 409 `proposal_stale` ("Cette proposition est périmée : le document a changé depuis. Relancez la demande."). A document has at most one active run; starting another returns 409 `run_in_progress`.
- **Why:** undo/redo, another accepted proposal or a concurrent instruction would otherwise apply operations to the wrong version.
- **Cost:** the teacher must relaunch a stale instruction; the UI handles two extra errors.

### ADR-026, Task chains: route_plan, answer, write_fr, classify, stt
Accepted · 2026-10-15 · supersedes ADR-009
- **Decision:** ordered model chains per task, `route_plan`, `answer`, `write_fr`, `classify` and `stt`, in YAML; no model name in code. For questions, `route_plan` returns the answer directly when the compact view is enough (typical case, 1 call); the `answer` chain is used only when the answer needs a larger part of the document (2 calls). There is no summarization chain: conversation history beyond the last N turns is truncated without AI in v1.
- **Why:** free models change without notice, so updates must not require a release; the agent merges routing and planning into one call, which a small routing model handles poorly; answering most questions in the routing call saves quota; summarization would cost calls outside the call budget.
- **Cost:** long conversations lose older context.

### ADR-027, Per-provider quota reset time zone and zero-quota key check
Accepted · 2026-10-15
- **Decision:** each provider in `models.yaml` declares `quota_reset_tz`; daily quota windows and daily-limit cooldowns follow it. The key test uses an authenticated `GET /models`, or, where the model list is public (OpenRouter), the equivalent authenticated zero-quota endpoint recorded in `PROVIDERS.md`.
- **Why:** providers do not all reset at UTC midnight (Gemini resets at midnight Pacific time); testing a key must not consume quota.
- **Cost:** one more value per provider to verify in T-306.

### ADR-028, SQLite files for local state
Accepted · 2026-10-15 · supersedes ADR-019
- **Decision:** app state (history, conversations, templates index, quota counters, settings) lives in `db/assistant.sqlite` (SQLAlchemy 2 + Alembic). LangGraph checkpoints live in a separate `db/checkpoints.sqlite` in WAL mode.
- **Why:** the checkpointer opens its own connection; a separate file avoids write-lock contention and keeps the Alembic schema independent of LangGraph's.
- **Cost:** two database files to handle in diagnostics and cleanup.

### ADR-029, LangGraph lazy-loaded behind a footprint gate
Accepted · 2026-10-15
- **Decision:** the agent package (and LangGraph) is imported on the first instruction, never at startup. Its cost is measured with the walking-skeleton tooling (ADR-035) when LangGraph is added (T-402). If it adds more than 40 MB idle RSS or more than 1.5 s cold start, a new ADR replaces it with an in-house state machine plus an interrupts table behind the same node interfaces.
- **Why:** LangGraph pulls `langchain-core` and its dependencies, which threaten the RAM, start-time and bundle budgets; ADR-015 rejected LiteLLM for the same reason.
- **Cost:** measurement work and a possible rewrite of the graph layer.

### ADR-030, Voice: Groq Whisper only in v1
Accepted · 2026-10-15 · supersedes ADR-014
- **Decision:** speech-to-text uses the `stt` chain (Groq Whisper, free, French forced). Local `faster-whisper` is moved to post-v1 (ticket T-703 in "Later").
- **Why:** the `faster-whisper`/`ctranslate2` runtime would be bundled even with the model downloaded on demand, breaking the 150 MB installer budget; target hardware is weak.
- **Cost:** no voice input offline in v1.

### ADR-031, Synthetic corpus in three layers; instruction targets by text or role
Accepted · 2026-10-15 · refines ADR-020
- **Decision:** T-005a builds python-docx files and `instructions.yaml`; T-005b adds raw-XML fixtures for what python-docx cannot produce, a committed binary `.doc`, and byte-deterministic output (fixed zip timestamps and docProps); T-005c, done by a human and non-blocking, adds "Word-saved" variants. `instructions.yaml` designates targets by text or role, never by block ID.
- **Why:** python-docx cannot produce several required structures and does not write Word's real XML; IDs of files without `paraId` are generated at import, so ID-based targets would be fragile.
- **Cost:** hand-written XML fixtures to maintain.

### ADR-032, Import by upload only; file paths only for export
Accepted · 2026-10-15
- **Decision:** `POST /documents/import` accepts only a multipart upload, with the size and zip-bomb limits. The frontend uses the WebView's file picker in Tauri, in the browser during development and in tests. The backend receives a path only for export (native save dialog); overwriting any existing file, including the original, requires an explicit `overwrite` flag sent after a French confirmation (consistent with ADR-006).
- **Why:** one code path for Tauri, development and tests; a browser or Playwright cannot provide local paths.
- **Cost:** the backend does not know where the original lives; "replace the original" means the teacher picks it in the save dialog.

### ADR-033, No table insertion inside a table cell in v1
Accepted · 2026-10-15
- **Decision:** `insert_table` targeting a paragraph inside a table cell is rejected by the validator with a French message.
- **Why:** nested tables are fragile in Word and in docx-preview and rare in teacher documents.
- **Cost:** the teacher restructures such layouts manually.

### ADR-034, `--fake-llm` startup flag for end-to-end tests
Accepted · 2026-10-15
- **Decision:** the backend accepts `--fake-llm <fixtures>`, which replaces every provider with the FakeLLM; packaged (frozen) builds refuse the flag with a startup error.
- **Why:** Playwright tests need the real backend without network access.
- **Cost:** a test-only code path in the shipped binary, guarded and tested.

### ADR-035, Packaging walking skeleton before the engine
Accepted · 2026-10-15
- **Decision:** right after the backend core (T-003), ticket T-006 packages a `/health`-only backend with PyInstaller onedir, starts it from Tauri, and records bundle size, cold start and idle RSS; the measurement is repeated after LangGraph is added.
- **Why:** packaging, footprint and antivirus problems can invalidate the stack; discovering them in the last milestone would be too late.
- **Cost:** early Rust and packaging work, later extended by T-801 and T-802.
