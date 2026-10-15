# Backlog

## How to use this backlog with Claude Code
1. Create the repository, copy `CLAUDE.md` to the root and the `docs/` folder, commit.
2. Open Claude Code in the repository and give it **one ticket at a time**, for example:
   > Implement ticket T-001 from docs/TICKETS.md. Follow CLAUDE.md: present your plan and wait for my approval before writing code.
3. Review the plan, approve or correct it, let it implement, review the diff and the test results, then move to the next ticket.
4. Follow the order of the milestones. A ticket can start only when the tickets in **Depends on** are done (inside an epic, IDs are not always in dependency order: for example T-305 comes before T-302).
5. Tick the box when a ticket is done (`- [x]`).

Size: **S** ≈ one short session, **M** ≈ one full session, **L** ≈ two sessions (consider splitting in the plan).

## Milestones
| Milestone | Tickets | Result |
|---|---|---|
| **M1 Foundation + engine** | T-001 → T-110 | A .docx can be read, changed by operations and versioned, fully tested on the corpus. |
| **M2 Templates + AI access** | T-201 → T-207, T-301 → T-306 | Templates learned from documents; free models reachable with fallbacks and quotas. |
| **M3 Agent + API** | T-401 → T-407, T-501 → T-504 | Full instruction flows work through the API with the fake model and live models. |
| **M4 Interface** | T-600 → T-610 | The teacher can do everything from the UI (in a browser during development). |
| **M5 Voice + desktop + release** | T-701 → T-703, T-801 → T-807 | Installable Windows app with voice, auto-update and user guide. |

---

## E0, Foundation

- [ ] **T-001 · Monorepo scaffold and tooling** · M · Depends on: –
  - Create the layout from ARCHITECTURE §5: `backend/` (uv project, `src/assistant_prof`, empty packages), `frontend/` (Vite React TS strict), `desktop/src-tauri/` (Tauri 2 app pointing to the frontend), `corpus/`, `docs/`.
  - Tooling: ruff, mypy strict, pytest (+ coverage), eslint, prettier, vitest, cargo clippy, pre-commit, `.editorconfig`, `.gitattributes` (LF, `*.docx binary`), `.gitignore`.
  - `justfile` with the commands listed in CLAUDE.md (stubs allowed for later ones, printing "not implemented: T-xxx").
  - README: prerequisites (Python 3.12, uv, Node LTS, pnpm, Rust stable, just) and quick start.
  - **Acceptance:** fresh clone → `just setup` → `just check` passes on Windows and Linux; `just dev` opens a Tauri window showing a placeholder page.

- [ ] **T-002 · CI pipeline** · S · Depends on: T-001
  - GitHub Actions: on push/PR, matrix ubuntu-latest + windows-latest: backend lint/types/tests, frontend lint/types/tests, `cargo clippy`. Cache uv, pnpm and cargo. `pip-audit` and `pnpm audit` (non-blocking warnings at first).
  - Dependabot for pip (uv), npm, cargo, actions.
  - **Acceptance:** CI green on both OSes; a failing test makes CI red.

- [ ] **T-003 · Backend core** · M · Depends on: T-001
  - `core/config.py` (pydantic-settings; CLI args `--port`, env `ASSISTANT_PROF_TOKEN`, data dir override for tests), `core/paths.py` (platformdirs: `%APPDATA%\AssistantProf`), `core/logging.py` (structlog JSON, rotating 5×5 MB, correlation ID context, redaction filter), `core/errors.py` (typed hierarchy + codes), `core/ids.py`, `core/clock.py` (injectable time).
  - `api/app.py` app factory; token middleware; problem-details handlers; `GET /health`, `POST /shutdown`; CORS for the Tauri origin.
  - Entry point `python -m assistant_prof --port N`.
  - **Acceptance:** requests without the token → 401; health returns version; logs are JSON and redact a fake key; tests cover all of it.

- [ ] **T-004 · Persistence layer** · S · Depends on: T-003
  - SQLAlchemy 2 engine/session for the SQLite file in the data dir, Alembic configured (programmatic upgrade on startup), base tables: `settings`, `documents`, `versions`. Repository pattern.
  - **Acceptance:** startup migrates an empty DB; a migration test upgrades from zero to head; repositories unit-tested on a temp DB.

- [ ] **T-005 · Synthetic test corpus and instruction set** · L · Depends on: T-001
  - `corpus/generator/` builds ≥ 14 .docx files that mimic real teacher documents, each with a README line describing what it stresses:
    1. clean exam with proper styles and auto-numbered questions;
    2. same exam formatted **by hand** (Normal style, manual bold/size, typed "1)" numbers, spaces for alignment);
    3. header made with a **table** (school | class | date) and a logo image;
    4. **bilingual Tunisian header** (Arabic RTL + French: "République Tunisienne / Ministère de l'Éducation");
    5. title in a **text box**; 6. two-column layout section;
    7. dotted and underscore **answer lines**; 8. QCM with a), b), c) choices;
    9. text with **tracked changes** and comments; 10. equations and a chart (locked content);
    11. long guide (≥ 30 pages, headings, TOC field); 12. file saved without `w14:paraId` (python-docx generated);
    13. dictation sheet with a support text and blanks; 14. answer key with a points table.
    Plus: an `.doc` renamed to `.docx` and a corrupt zip for error tests.
  - `corpus/instructions.yaml`: ≥ 30 French instructions covering formatting, rewording, generation, creation and questions; each with target document, expected intent, expected operation types/targets (or checks), and whether the fast path should catch it.
  - **Acceptance:** `just corpus` regenerates everything deterministically; every file opens in python-docx (except the deliberate bad ones); the instruction file validates against a schema.

## E1, Document engine

- [ ] **T-101 · DocModel reader with stable IDs** · L · Depends on: T-003, T-005 · ARCH §7.2, §7.4
  - Blocks for body, table cells, headers/footers; location, style, list info, text, format summary, mixed-formatting flag.
  - IDs from `w14:paraId`; generate missing ones (unique, 8 hex, < 0x80000000) on the working copy.
  - Locked-content detection with reasons; document-level info (sections, styles, numbering, tables, warnings).
  - **Acceptance:** every corpus file loads; IDs unique and stable across save/reload; locked blocks correctly flagged on files 5, 9, 10; header/footer blocks found on 3 and 4; tests per file.

- [ ] **T-102 · Inline markup ⇄ runs** · M · Depends on: T-101 · ARCH §7.3
  - Parser and serializer for `**`, `*`, `__`, `^^`, escaping rules; runs → markup relative to dominant formatting; markup → runs cloning nearest original run properties.
  - **Acceptance:** hypothesis round-trip tests; mixed paragraphs from corpus file 2 survive rewrite of identical text with no visible change.

- [ ] **T-103 · Model-facing serialization** · M · Depends on: T-101 · ARCH §7.5
  - Compact view, outline view, section chunking, token estimate, data delimiting.
  - **Acceptance:** snapshot tests; long guide (file 11) chunked under a configurable budget; text containing fake instructions stays inside the data delimiters.

- [ ] **T-104 · Operation schemas and validator** · M · Depends on: T-101 · ARCH §7.6
  - Pydantic discriminated union for the full catalogue; JSON Schema export (used later for structured output); validator with all rules; French error messages for the teacher + technical messages for the repair loop.
  - **Acceptance:** each rule has passing and failing tests; hypothesis fuzzing never crashes the validator; schema export snapshot.

- [ ] **T-105 · Executor: text operations** · L · Depends on: T-102, T-104 · ARCH §7.7
  - `rewrite`, `replace_in`, `insert_after/before`, `delete`, `move`; transaction on a copy; exemplar cloning helper; per-operation error report.
  - **Acceptance:** golden tests on corpus files 1, 2, 3, 7, 13; failure in the 3rd of 5 operations leaves the document unchanged.

- [ ] **T-106 · Executor: formatting operations** · M · Depends on: T-105
  - `set_style` (incl. creating a style from a base), `set_font`, `set_alignment`, `set_spacing`, `set_indent`, `set_list` (bullet/number/none, formats, restart via new `w:num`).
  - **Acceptance:** golden tests; numbering restart verified in XML and by reopening; Word-compatibility check via LibreOffice is **not** required.

- [ ] **T-107 · Executor: page and structure operations** · M · Depends on: T-105
  - `set_margins`, `set_orientation` (swap page size), `page_break_before`, `insert_table`, `insert_answer_lines`, `apply_role_format` (stub until T-205 provides exemplars).
  - **Acceptance:** golden tests incl. multi-section document; tables inserted inside the body and after a table cell paragraph are rejected or handled as specified.

- [ ] **T-108 · Atomic save, integrity check, no-op round trip** · M · Depends on: T-105
  - Temp write + fsync + reopen + zip check + `os.replace`; normalized-XML comparison utility.
  - **Acceptance:** no-op round trip equivalent on all corpus files; simulated crash during save leaves the previous version intact; Windows path edge cases (spaces, accents, long paths) tested.

- [ ] **T-109 · Proposal diff** · S · Depends on: T-105
  - Block-level diff (added/removed/changed/format-only) + word-level text diff; JSON shape for the UI.
  - **Acceptance:** unit tests on crafted pairs; diff of a no-op is empty.

- [ ] **T-110 · Versions and workspaces** · M · Depends on: T-004, T-108 · ARCH §7.9
  - Import (copy original, assign IDs), versions table, head pointer, undo/redo, export copy, "replace original" with explicit flag, retention policy job.
  - **Acceptance:** integration tests of the full lifecycle; original file hash unchanged after any sequence of operations.

## E2, Template learning

- [ ] **T-201 · Container extraction** · M · Depends on: T-101 · ARCH §8.2
  - Copy styles, numbering, theme, settings, sections, headers/footers (with images and RTL text); empty the body keeping the final section properties.
  - **Acceptance:** container of corpus files 1, 3, 4 opens, shows the same header/footer and page setup, contains no body text.

- [ ] **T-202 · Role taxonomy and rule-based classifier** · L · Depends on: T-101 · ARCH §8.3, §8.4
  - Feature extraction; French rules in `config/rules.fr.yaml`; scoring with confidence; deterministic output.
  - **Acceptance:** labelled ground truth for ≥ 6 corpus files (stored next to them); report per role; ≥ 80 % accuracy rules-only on clean files, measured and printed by a test.

- [ ] **T-203 · LLM-assisted classification** · M · Depends on: T-202, T-304
  - One batched call for blocks under the threshold; schema-validated; merges with rule results; uses teacher corrections as few-shots when available.
  - **Acceptance:** with FakeLLM, low-confidence blocks are sent in one call and merged; prompt snapshot test; live eval documented in T-207.

- [ ] **T-204 · Template profile builder** · M · Depends on: T-201, T-202
  - `profile.json` schema v1 (ARCH §8.6), exemplar selection per role (most representative paragraph), structure inference, conventions detection (tu/vous, points format, section label, total), short excerpts.
  - **Acceptance:** profiles for corpus files 1, 2, 7, 8, 13 match expected snapshots; schema versioning test.

- [ ] **T-205 · Renderer by exemplar cloning** · L · Depends on: T-204, T-106 · ARCH §8.7
  - Role-tagged content → document from container; numbering restarts per section; answer lines; tables; missing styles/numbering copied; fallback chain for unknown roles; completes `apply_role_format`.
  - **Acceptance:** rendering the same content with templates from files 1 and 2 gives two documents that each match their source's look (golden tests on formatting properties).

- [ ] **T-206 · Template library and built-in templates** · M · Depends on: T-205, T-004
  - CRUD, storage layout, index table, name/description, source hash, created/updated; two built-in templates generated through the pipeline at build time.
  - **Acceptance:** integration tests; built-ins available on a fresh install.

- [ ] **T-207 · Template learning evaluation** · S · Depends on: T-203, T-204
  - `just eval-templates`: accuracy per role (rules only, rules + FakeLLM replay; optional live run), confusion matrix, saved report in `docs/reports/`.
  - **Acceptance:** report generated; target ≥ 90 % with LLM pass on the synthetic corpus, or gaps documented with follow-up tickets.

## E3, LLM gateway

- [ ] **T-301 · Provider configuration and key storage** · M · Depends on: T-003
  - `models.yaml` schema (providers, models, limits, capabilities, task chains) with user override merge; `keyring` storage; key test call (cheapest possible request) per provider.
  - **Acceptance:** schema validation errors are clear; keys never appear in logs (tested); keyring mocked in tests.

- [ ] **T-302 · Router with fallback chains** · L · Depends on: T-301, T-305 · ARCH §9.3
  - OpenAI-compatible client over `httpx`; per-provider quirks isolated in small adapters; timeouts; error classification (rate limit minute/day, server, timeout, auth, invalid output, offline); cooldowns from headers or backoff; returns result + model used + timings.
  - **Acceptance:** tests with a mock transport for each error class: correct next model, correct cooldown, offline mode without cooldowns; no model names in code (grep test).

- [ ] **T-303 · Quota tracker** · M · Depends on: T-302, T-004
  - SQLite counters per model per minute/day (UTC), header reconciliation, pre-call checks, `/quota` data shape.
  - **Acceptance:** time-controlled tests (injected clock) for minute and day windows and midnight reset.

- [ ] **T-304 · Structured output layer** · M · Depends on: T-302, T-104
  - json_schema → json_object → text modes by capability; tolerant parsing; Pydantic validation; one repair retry with the error; then fallback.
  - **Acceptance:** tests for fenced JSON, trailing commas, wrong types, missing fields, and the retry path.

- [ ] **T-305 · FakeLLM and recorded fixtures** · S · Depends on: T-003
  - Scripted fake (queue or keyed by task + prompt hash), recorder for `eval-live` runs to create replay fixtures, guard that fails any test attempting real network.
  - **Acceptance:** used by T-302 tests; network guard proven by a test.

- [ ] **T-306 · Verify current free models and fill defaults** · S · Depends on: T-301
  - Check each provider's current free models, limits, OpenAI-compatible endpoint behaviour and JSON support from official pages/consoles; write `docs/PROVIDERS.md` (dated, with links) and `models.default.yaml`; contract tests with recorded responses.
  - **Acceptance:** at least 2 models per task chain; a live smoke script succeeds with real keys provided by the user (manual).

## E4, Agent

- [ ] **T-401 · Fast path rules** · M · Depends on: T-104
  - French patterns → operations (bold/italic/underline, font name/size, alignment, spacing, margins, orientation, lists) targeted at the selection or at a role; ambiguity → no match.
  - **Acceptance:** all fast-path instructions in `instructions.yaml` matched with correct operations; no false matches on the others.

- [ ] **T-402 · Graph skeleton, state and checkpointer** · M · Depends on: T-305, T-004 · ARCH §10
  - LangGraph state, nodes as stubs, SQLite checkpointer, conversation memory (last N turns + summary), correlation IDs, event emission interface.
  - **Acceptance:** a stubbed run goes from instruction to a pending proposal and resumes after a simulated app restart.

- [ ] **T-403 · Edit planning (route + plan)** · L · Depends on: T-402, T-103, T-304, T-401
  - Prompt `route_plan.md` (French, few-shots), target resolution (selection → role map → model), question answering branch.
  - **Acceptance:** `just eval` with FakeLLM replay passes for edit instructions; average ≤ 1.3 LLM calls per edit instruction.

- [ ] **T-404 · Create flow (outline → content)** · L · Depends on: T-403, T-205
  - Outline node + interrupt with editable outline; `write_content` per section or whole doc by context budget, using profile conventions and excerpts; renderer to a new document.
  - **Acceptance:** creating a document from built-in and learned templates works end to end with FakeLLM; outline edits are respected.

- [ ] **T-405 · Validation, repair and proposal assembly** · M · Depends on: T-403, T-109
  - Validator errors → one repair call → proposal (executor on copy, diff, reasons) → interrupt; accept all / subset / reject.
  - **Acceptance:** invalid first answer repaired in tests; subset acceptance re-validates and applies only chosen ops.

- [ ] **T-406 · Progress events** · S · Depends on: T-402
  - Event types from ARCH §10.3 emitted by nodes; French labels.
  - **Acceptance:** event sequence snapshot per flow.

- [ ] **T-407 · Agent evaluation harness** · M · Depends on: T-403, T-404
  - `just eval` (replay) and `just eval-live`: correctness checks from `instructions.yaml`, calls per instruction, latency, fallbacks used; report in `docs/reports/`.
  - **Acceptance:** report generated; live run done once with the user's keys and results reviewed.

## E5, API

- [ ] **T-501 · Documents API** · M · Depends on: T-110, T-101
  - Routes from ARCH §12 for documents, files, versions, undo/redo, export; upload limits and zip-bomb guard.
  - **Acceptance:** integration tests incl. limits and corrupt files (French error codes).

- [ ] **T-502 · Instructions, proposals and outlines API (SSE)** · M · Depends on: T-405, T-406, T-501
  - SSE stream, accept/reject/subset, outline approval, cancellation.
  - **Acceptance:** integration tests for each flow with FakeLLM; client disconnect cancels cleanly.

- [ ] **T-503 · Templates API** · S · Depends on: T-206, T-203
  - Learn, review data (blocks + roles + colours), role corrections, save, list, delete.
  - **Acceptance:** integration tests.

- [ ] **T-504 · Settings, keys, quota, diagnostics API + TS client generation** · M · Depends on: T-301, T-303
  - Routes; diagnostics zip redaction; `just gen-api` producing the frontend client; CI check that the generated client is up to date.
  - **Acceptance:** tests; redaction verified on a zip containing fake keys and document text.

## E6, Interface

- [ ] **T-600 · Spike: docx-preview block mapping** · M · Depends on: T-501
  - Prototype: render corpus files with docx-preview, map rendered paragraphs to block IDs (order + normalized text), click-select and highlight; measure mapping accuracy per file; decide keep vs fallback editing view (ARCH §13.2). Write an ADR with the result.
  - **Acceptance:** accuracy table for all corpus files; ADR written; throwaway code removed or moved into T-604.

- [ ] **T-601 · App shell and design system** · M · Depends on: T-001
  - Routing, layout, Tailwind + shadcn/ui, French i18n setup, theme (calm, readable, large touch targets), error boundaries, connection to backend via Tauri command (dev fallback: env vars).
  - **Acceptance:** screens navigable with placeholders; vitest for i18n completeness (no missing keys).

- [ ] **T-602 · First-launch wizard** · M · Depends on: T-601, T-504
  - Welcome, keys step with links and "Tester", training-use disclosure, optional first template, finish.
  - **Acceptance:** Playwright flow with mocked key test; cannot finish without one valid provider.

- [ ] **T-603 · Home screen** · S · Depends on: T-601, T-501
  - Recent documents, open via native dialog (browser file input in dev), new document entry, templates entry.
  - **Acceptance:** component and E2E tests.

- [ ] **T-604 · Editor: page view with selection** · L · Depends on: T-600, T-603
  - docx-preview view, block selection (click, shift-click), role colours toggle, highlight of proposal targets, zoom.
  - **Acceptance:** E2E: select two blocks, selection IDs sent with the instruction.

- [ ] **T-605 · Editor: chat panel** · M · Depends on: T-604, T-502
  - Messages, input, Ctrl+Entrée, shortcut chips (configurable prompts), progress steps from SSE, model badge, French errors with retry.
  - **Acceptance:** E2E with FakeLLM for an edit instruction and a question.

- [ ] **T-606 · Editor: proposals, versions, export** · M · Depends on: T-605
  - Proposal panel (reasons, word diff, accept all/subset/reject), versions timeline, undo/redo, export dialog, quota indicator.
  - **Acceptance:** E2E: propose → accept subset → undo → redo → export.

- [ ] **T-607 · Create flow UI** · M · Depends on: T-606, T-404
  - Template picker, description form or free text, outline editor (reorder, rename, delete), generation progress, open result in editor.
  - **Acceptance:** E2E create flow with FakeLLM.

- [ ] **T-608 · Template learning wizard and library** · M · Depends on: T-604, T-503
  - Choose file → analysis → role review (colours, legend, click to change role) → name → save; library list, rename, delete.
  - **Acceptance:** E2E: learn template from corpus file 2, correct one role, use it in the create flow.

- [ ] **T-609 · Settings screen** · S · Depends on: T-602
  - Keys, advanced model chains editor (with validation), quota dashboard, voice settings, retention, diagnostics export, about.
  - **Acceptance:** component tests; invalid chain config rejected with a French message.

- [ ] **T-610 · States, accessibility and polish** · M · Depends on: T-606, T-607, T-608
  - Empty, loading, offline, quota-exhausted, backend-restarting states; keyboard navigation; focus management; 125–150 % scaling check; consistent French copy review.
  - **Acceptance:** axe checks in Playwright with no serious violations; manual checklist done.

## E7, Voice

- [ ] **T-701 · STT service and Groq provider** · S · Depends on: T-302
  - STT interface, Groq Whisper via the gateway chain `stt`, `POST /stt` (≤ 60 s, French), errors.
  - **Acceptance:** tests with recorded responses; quota counted.

- [ ] **T-702 · Microphone UI** · M · Depends on: T-701, T-605
  - Push-to-talk button and key, level meter, permission handling in WebView2, transcript inserted for editing before sending.
  - **Acceptance:** component tests with a mocked MediaRecorder; manual test inside Tauri on Windows.

- [ ] **T-703 · Optional local STT** · M · Depends on: T-701, T-609
  - Hardware check (RAM, AVX2), on-demand model download with progress and checksum, `faster-whisper` `base` int8, lazy import; off by default.
  - **Acceptance:** disabled path adds no startup cost (measured); enabled path transcribes a French sample in tests marked `slow`.

## E8, Desktop and release

- [ ] **T-801 · Tauri shell and sidecar lifecycle** · L · Depends on: T-003, T-601 · ARCH §4
  - Port + token handshake, health wait, crash restart once, graceful shutdown + process-tree kill, single instance, window state, native dialogs, CSP and minimal capabilities.
  - **Acceptance:** manual + scripted tests on Windows: kill backend → restarts; close window → no orphan process.

- [ ] **T-802 · Backend packaging (PyInstaller onedir)** · M · Depends on: T-801
  - Spec file, hidden imports, data files (prompts, config, built-in templates, migrations), no UPX, size report, startup time measurement.
  - **Acceptance:** packaged backend starts and passes `/health` on a clean Windows runner; size and start time recorded against budgets.

- [ ] **T-803 · Windows installer** · M · Depends on: T-802
  - Tauri NSIS bundle, per-user, French, WebView2 bootstrapper, icons, metadata, uninstall keeps or removes user data (asks).
  - **Acceptance:** install/uninstall on a clean Windows VM without admin rights.

- [ ] **T-804 · Auto-update** · S · Depends on: T-803
  - Updater key pair (private key in GitHub secrets), update check on start (non-blocking), French prompt.
  - **Acceptance:** update from version N to N+1 via a test release.

- [ ] **T-805 · Release workflow** · S · Depends on: T-803, T-002
  - Tag → build on windows-latest → artifacts + updater manifest → draft GitHub release with changelog from commits.
  - **Acceptance:** a test tag produces a downloadable installer.

- [ ] **T-806 · Packaged smoke test and low-end QA** · M · Depends on: T-805
  - PowerShell smoke test in CI (silent install, launch, health, open a corpus doc via API, exit, uninstall); `docs/QA_CHECKLIST.md`; manual run on a 4 GB RAM Windows VM with measurements vs budgets.
  - **Acceptance:** smoke test green in CI; QA report with numbers in `docs/reports/`.

- [ ] **T-807 · User guide (French)** · S · Depends on: T-806
  - `docs/user-guide-fr.md` (+ PDF export): installation with the SmartScreen step, getting free API keys (with links), first document, learning a template, voice, troubleshooting, exporting diagnostics.
  - **Acceptance:** a non-technical tester follows it from zero to a first edited document.
