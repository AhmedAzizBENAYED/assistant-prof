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

### ADR-036, Monorepo tooling layout
Accepted · 2026-10-15
- **Decision:**
  - one pnpm workspace at the root (`frontend`, `desktop`) with a single lockfile; `desktop/package.json` holds only the Tauri CLI, so the frontend stays a plain Vite app;
  - the `justfile` uses PowerShell on Windows and `sh` elsewhere; recipes use `uv --directory`, `pnpm --dir` and `cargo --manifest-path` instead of `cd` so the same lines run in both shells;
  - recipes for later tickets are stubs that print `not implemented: T-xxx` and exit 1; `just check` never calls a stub;
  - the backend uses the `uv_build` build backend and is pinned to Python 3.12;
  - `rust-toolchain.toml` sits at the repository root (rustup resolves it from the working directory, not from `--manifest-path`) and installs `rustfmt` and `clippy`;
  - TypeScript is pinned to 6.0.x because typescript-eslint does not support TypeScript 7 yet; lift the pin when it does, and remove the matching `ignore` rule (TypeScript semver-major) in `.github/dependabot.yml` at the same time;
  - pre-commit runs through `uvx` (pinned version in the `justfile`) and only runs fast checks; mypy and the tests run in `just check`.
- **Why:** one command set for Windows and Linux developers and CI; fewer tools to install; lockfiles for every stack.
- **Cost:** PowerShell 5.1 reports every failing command as exit code 1 (the exact code is lost, failure is not).
- **Open point (T-801):** Tauri should pass its app data directory to the backend at startup (CLI argument) so all user data lives under one folder chosen by the shell; ARCHITECTURE §4 and §7.9 are updated when T-801 is implemented.

### ADR-037, CI design and minutes budget
Accepted · 2026-10-15
- **Context:** the repository is public, so GitHub Actions minutes are free; it may become private later, where Windows minutes count double against the free quota. CI should be fast and frugal either way.
- **Decision:**
  - **development workflow:** a single developer commits directly to `main`; no feature branches, no pull requests of their own. The only PRs are Dependabot's: CI runs on them and the developer merges them once CI is green. The assistant commits but never pushes; the developer pushes manually and checks the CI run, and a reported red run is fixed before any other work starts (CLAUDE.md, step 6). No GitHub repository settings are relied on (no rulesets, branch protection or security features); CI and Dependabot are configured only by files in the repository;
  - one workflow (`ci.yml`) triggered by `push` to `main`, `pull_request` targeting `main` (in practice Dependabot only), `workflow_dispatch` and a weekly schedule;
  - `concurrency` cancels superseded runs on the same ref (a quick follow-up push replaces the previous run);
  - a `changes` job (`dorny/paths-filter`: a push is diffed against the previous head of `main`, a PR against its base branch) enables the backend, frontend and desktop jobs only when their paths, the `justfile` or the workflow changed; scheduled and manual runs enable everything;
  - each stack job runs its `just check-*` recipe on `ubuntu-latest` and `windows-latest`, so CI and local checks cannot drift;
  - caches: `setup-uv` (keyed on `uv.lock`, plus the managed Python), `setup-node` pnpm store, `Swatinem/rust-cache` for `desktop/src-tauri/target`, saved from `main` only (PR caches are scoped to their PR, never reused, and would eat the 10 GB quota);
  - a `ci-ok` job aggregates the results (skipped counts as passed): the single status to look at after a push;
  - `pip-audit`, `pnpm audit` and `cargo audit` (`just audit-*`) run in a non-blocking job when a lockfile changes and weekly; findings surface as a workflow warning. `cargo-audit` and `just` are installed as prebuilt binaries (`taiki-e/install-action`);
  - third-party actions are pinned to commit SHAs; `permissions: contents: read` by default; checkout does not persist credentials;
  - Dependabot: monthly version updates for uv, npm, cargo and actions, minor and patch grouped per ecosystem, at most 3 open PRs each (no Dependabot security updates, since they are a repository setting);
  - `actionlint` runs as a pre-commit hook (`actionlint-py`, ships the binary, no Go toolchain).
- **Why:** direct pushes keep a solo workflow simple, and checking `ci-ok` after each push still catches breakage at once; a full warm run costs a few minutes, a docs-only commit about one; supply-chain risk from tag-moved actions is removed; Dependabot noise and the CI runs it triggers stay bounded.
- **Cost:** audits are warnings, not gates, until the dependency set settles; tighten them later. Changes outside the filtered paths (e.g. `.pre-commit-config.yaml`) do not trigger the stack jobs.

### ADR-038, Backend startup contract and ready-line port handshake
Accepted · 2026-10-15
- **Context:** ARCHITECTURE §4 had Tauri pick a free port, pass it to the backend and poll `/health`. Between the moment Tauri checks the port and the moment the backend binds it, another process can take it (a race), and polling adds latency to the cold start.
- **Decision:**
  - the backend accepts `--port 0`, binds 127.0.0.1 on an OS-assigned port and, once listening, writes exactly one line to stdout: `{"event":"ready","port":<port>,"version":"<version>"}`. stdout carries nothing else: logs go to the log file (and stderr in dev mode), and `sys.stdout` is redirected to stderr for the whole run so a stray `print` cannot break the handshake. Tauri (T-006, T-801) reads this line instead of choosing a port and polling `/health`;
  - the session token comes only from `ASSISTANT_PROF_TOKEN` (no `--token` argument: command lines are visible to other processes) and must be at least 32 characters; startup errors exit with code 2 and an English message on stderr that never echoes input values;
  - `--dev` (Vite dev origin in CORS, logs copied to stderr, `/docs`) is refused in packaged (frozen) builds, like `--fake-llm` (ADR-034);
  - `--data-dir` overrides the data directory; it is what T-801 uses to pass the Tauri app data directory (open point of ADR-036);
  - CORS origins are a setting (default `http://tauri.localhost`, `https://tauri.localhost`); the dev origin is added only in dev mode;
  - `just backend` runs the backend alone in dev mode with a fresh random token printed once (no fixed dev token anywhere), `--port 0` and data in `backend/build/dev-data`;
  - Uvicorn runs with its lightest settings (`h11`, no websockets, asyncio loop, no access log: the request middleware logs each request with its correlation ID), and middleware is pure ASGI so streaming responses (SSE) are not buffered.
- **Why:** no port race, a faster and simpler handshake, and no secret on the command line.
- **Cost:** the Rust side must read the child's stdout line by line (with a timeout) instead of only polling HTTP; nothing in the backend may ever write to the real stdout.
- **Amended by ADR-039 (T-006):** the backend also accepts `--exit-on-stdin-eof`; the desktop shell always passes it and keeps the backend's stdin open, so the backend shuts down when the shell dies.

### ADR-039, Sidecar from `std::process`, parent death through stdin, measurement on USS
Accepted · 2026-10-15
- **Context:** T-006 starts the packaged backend from the Tauri shell and measures the result (ADR-035). The shell can die without running any exit code (crash, killed from the Task Manager), which would leave an orphaned backend holding memory and its log file. Summed RSS of the WebView2 processes also counts their shared pages several times.
- **Decision:**
  - **parent-death detection:** the backend accepts `--exit-on-stdin-eof` (opt-in, off for `just backend` and hand runs). With it, a daemon thread reads and discards stdin; at end of file it triggers the same graceful shutdown as `POST /shutdown` (log event `shutdown.stdin_eof`). The shell always passes the flag, spawns the backend with stdin piped and keeps the write end open for its whole life; the OS closes it when the shell exits for any reason. On a normal exit the shell still sends `POST /shutdown`, closes stdin and kills the backend after 3 s;
  - **spawning:** the shell uses `std::process::Command`, not the `tauri-plugin-shell` sidecar feature: that feature expects a single `externalBin` file, which does not fit a PyInstaller onedir folder, and would add a plugin and a capability. On Windows the backend (a console program, so its stdout is a real pipe) is started with `CREATE_NO_WINDOW`;
  - **health check:** the shell sends its one local `GET /health` (and `POST /shutdown`) over a hand-written HTTP/1.1 request on `TcpStream`, instead of adding an HTTP client crate. The token is 32 bytes from `getrandom`, hex-encoded; `getrandom`, `serde` and `serde_json` were already in the dependency tree through Tauri;
  - **locating the backend:** `ASSISTANT_PROF_BACKEND_EXE`, else `backend/dist/assistant-prof-backend/` in the repository (built by `just build-backend`). T-803 switches the default to the installer's resource directory; `bundle.resources` is not set before then, because tauri-build fails when the folder does not exist (as in CI);
  - **reporting:** the shell writes one JSON line to its stdout, `backend_healthy` (with `elapsed_ms`, `port`, `backend_pid`, `version`) or `backend_failed` (English error). `just measure` reads it; T-801 replaces the failure path with the French error screen;
  - **measurement (`just measure`):** the release shell and the packaged backend, 5 runs each from fresh temporary data directories (`ASSISTANT_PROF_DATA_DIR`). Whole-app runs come first after the build, so their first run includes the antivirus scan and cold cache of a new build; the report gives the first run and the median. Cold start ends at the first authorised `/health` 200. Memory is sampled after 10 s idle, per process and in total, as RSS and USS; **budgets are judged on USS**, RSS is kept for reference. Whole app = the shell and all its descendants (WebView2, the backend and its console host). After each whole-app run the shell is killed and the backend must exit by itself within 10 s. A true cold start after a reboot stays a manual check;
  - **shutdown deadline** (amendment, 2026-10-15, T-006 follow-up): once a shutdown is requested, by stdin end of file or `POST /shutdown`, a 5 s timer starts (`SHUTDOWN_DEADLINE_S`); if the graceful shutdown has not completed by then (a stuck request, task or lifespan hook), the backend logs `shutdown.forced` at warning level, flushes its log handlers and calls `os._exit(0)`. A second request does not restart the timer; the timer is cancelled as soon as the server has stopped, so it never fires in in-process tests. The shell's 3 s kill on a normal exit (ARCH §4) stays as the outer limit; the deadline covers the stdin path, where nothing else would ever kill the backend;
  - PyInstaller is in a separate `packaging` dependency group (not installed by CI or `just setup`); psutil and its type stubs are dev dependencies, because `measure.py` is type-checked and tested in `just check`.
- **Why:** no orphaned backend whatever happens to the shell, without a watchdog or a Windows Job Object; no extra crates or plugins in the thin shell; memory figures that do not double-count shared pages.
- **Cost:** a background thread in the backend; the shell's HTTP code handles only the two lifecycle calls (anything richer belongs to the frontend); the repository default path is compiled into the shell until T-803. T-801 may add a Job Object for process-tree kill on top of the stdin signal.
