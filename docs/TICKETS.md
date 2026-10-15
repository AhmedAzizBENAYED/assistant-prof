# Backlog

## How to use this backlog with Claude Code
1. Create the repository, copy `CLAUDE.md` to the root and the `docs/` folder, commit.
2. Open Claude Code in the repository and give it **one ticket at a time**, for example:
   > Implement ticket T-001 from docs/TICKETS.md. Follow CLAUDE.md: present your plan and wait for my approval before writing code.
3. Review the plan, approve or correct it, let it implement, review the diff and the test results, then move to the next ticket.
4. Follow the order of the milestones. A ticket can start only when the tickets in **Depends on** are done (inside an epic, IDs are not always in dependency order: for example T-305 comes before T-302, and T-006 comes right after T-003).
5. Tick the box when a ticket is done (`- [x]`).
6. Tickets marked **(human)** are done by a person, not by Claude Code. **Conditional** tickets are done only if their trigger happens.

Size: **S** ≈ one short session, **M** ≈ one full session, **L** ≈ two sessions (consider splitting in the plan).

## Milestones
| Milestone | Tickets | Result |
|---|---|---|
| **M1 Foundation + engine** | T-001 → T-006 (T-005 split into T-005a, T-005b), T-101 → T-110 | Packaging path proven and measured; a .docx can be read, changed by operations and versioned, fully tested on the corpus. T-005c (human) is non-blocking. |
| **M2 Templates + AI access + mapping spike** | T-201 → T-208, T-301 → T-306, T-600 | Templates learned from documents; roles classified on import; free models reachable with fallbacks and quotas; page-view mapping strategy decided. |
| **M3 Agent + API** | T-401 → T-407, T-501 → T-504 | Full instruction flows work through the API with the fake model and live models. |
| **M4 Interface** | T-601 → T-611 (T-611 only if T-600 chooses the fallback) | The teacher can do everything from the UI (in a browser during development). |
| **M5 Voice + desktop + release** | T-701, T-702, T-801 → T-807 (T-805 merged into T-804) | Installable Windows app with voice, auto-update and user guide. |
| **Later (post-v1)** | T-703 | Not scheduled. |

---

## E0, Foundation

- [x] **T-001 · Monorepo scaffold and tooling** · M · Depends on: –
  - Create the layout from ARCHITECTURE §5: `backend/` (uv project, `src/assistant_prof`, empty packages), `frontend/` (Vite React TS strict), `desktop/src-tauri/` (Tauri 2 app pointing to the frontend), `corpus/`, `docs/`.
  - Tooling: ruff, mypy strict, pytest (+ coverage), eslint, prettier, vitest, cargo clippy, pre-commit, `.editorconfig`, `.gitattributes` (LF, `*.docx binary`, `*.doc binary`), `.gitignore`.
  - `justfile` with the commands listed in CLAUDE.md (stubs allowed for later ones, printing "not implemented: T-xxx").
  - README: prerequisites (Python 3.12, uv, Node LTS, pnpm, Rust stable, just; on Windows MSVC Build Tools with the Windows SDK; on Linux the Tauri system packages) and quick start.
  - **Acceptance:** fresh clone → `just setup` → `just check` passes on Windows and Linux; `just dev` opens a Tauri window showing a placeholder page.

- [x] **T-002 · CI pipeline** · S · Depends on: T-001
  - GitHub Actions: on push/PR, matrix ubuntu-latest + windows-latest: backend lint/types/tests, frontend lint/types/tests, `cargo clippy` (ubuntu installs `libwebkit2gtk-4.1-dev` and the other Tauri system packages). Cache uv, pnpm and cargo. `pip-audit` and `pnpm audit` (non-blocking warnings at first).
  - Dependabot for pip (uv), npm, cargo, actions.
  - **Acceptance:** CI green on both OSes; a failing test makes CI red.

- [x] **T-003 · Backend core** · M · Depends on: T-001
  - `core/config.py` (pydantic-settings; CLI args `--port`, env `ASSISTANT_PROF_TOKEN`, data dir override for tests), `core/paths.py` (platformdirs: `%APPDATA%\AssistantProf`), `core/logging.py` (structlog JSON, rotating 5×5 MB, correlation ID context, redaction filter), `core/errors.py` (typed hierarchy + codes), `core/ids.py`, `core/clock.py` (injectable time).
  - `api/app.py` app factory; token middleware; problem-details handlers; `GET /health`, `POST /shutdown`; CORS for `http://tauri.localhost` and, in dev mode only, the Vite dev origin.
  - Entry point `python -m assistant_prof --port N`.
  - **Acceptance:** requests without the token → 401; health returns version; CORS allows only the listed origins (dev origin only in dev mode); logs are JSON and redact a fake key; tests cover all of it.

- [x] **T-006 · Packaging walking skeleton** · M · Depends on: T-003 · ARCH §4, §16 · ADR-035
  - PyInstaller onedir build (no UPX) of the backend exposing only `/health`.
  - Minimal Tauri Rust code: pick a free port, generate the session token, spawn the packaged backend, wait for `/health`, kill it on exit (T-801 hardens this later).
  - Re-runnable measurement script, exposed as `just measure` (add it to the CLAUDE.md command table): backend bundle size, cold start until the first authorised `/health` 200, idle RSS of the backend and of the whole app. Results written to `docs/reports/`.
  - The measurement is repeated after LangGraph is added (T-402) against the gate in ADR-029.
  - **Note (ADR-038):** use the ready-line handshake instead of picking a port and polling `/health`: spawn the backend with `--port 0` and the token in `ASSISTANT_PROF_TOKEN`, read the `{"event":"ready","port":…}` line from its stdout, then call the authorised `/health` on that port. Cold start is measured until that first `/health` 200.
  - **Acceptance:** on Windows, the Tauri app starts the packaged backend and gets an authorised `/health`; report with the three numbers compared with the ARCHITECTURE §2 budgets.

- [x] **T-004 · Persistence layer** · S · Depends on: T-003
  - SQLAlchemy 2 engine/session for `db/assistant.sqlite` in the data dir, Alembic configured (programmatic upgrade on startup), base tables: `settings`, `documents`, `versions`. Repository pattern.
  - **Acceptance:** startup migrates an empty DB; a migration test upgrades from zero to head; repositories unit-tested on a temp DB.

- [x] **T-005a · Basic test corpus (python-docx) and instruction set** · M · Depends on: T-001 · ADR-031, ADR-041
  - `corpus/generator/` builds with python-docx the following files, each with a README line describing what it stresses:
    1. clean exam with proper styles and auto-numbered questions;
    2. same exam formatted **by hand** (Normal style, manual bold/size, typed "1)" numbers, spaces for alignment);
    3. header made with a **table** (school | class | date) and a logo image;
    4. **bilingual Tunisian header** (Arabic RTL + French: "الجمهورية التونسية / République Tunisienne", "وزارة التربية / Ministère de l'Éducation", with `w:bidi` and `w:rtl`), moved from T-005b;
    7. dotted and underscore **answer lines**, typed and drawn by a tab stop with a dot leader; 8. QCM with a), b), c) choices;
    12. file saved without `w14:paraId` (plain python-docx output);
    13. dictation sheet with a support text and blanks; 14. answer key with a points table.
    Plus a corrupt zip for error tests.
  - Realism spread across the files: French typography (U+00A0/U+202F before `: ; ? !`, ’), manual line breaks and empty paragraphs as spacing, varied points formats ("(2 pts)", "/2", "2 points") and "Exercice n°1 :" labels, mixed fonts (Times New Roman, Arial, Comic Sans MS), a conjugation grid to fill in, a page break between two parts.
  - python-docx writes no `w14:paraId`: every file except 12 gets Word-style `w14:paraId`/`w14:textId` and namespace declarations added by a post-processing step, so the reader is tested on both cases. The same step makes the output byte-deterministic (fixed zip timestamps and order, fixed `docProps/core.xml` dates and author), moved from T-005b.
  - `corpus/instructions.yaml`: ≥ 30 French instructions covering formatting, rewording, generation, creation and questions; each with target document, expected intent, expected operation types (by name) and targets, and whether the fast path should catch it; ≥ 5 typed like a hurried teacher and ≥ 3 near-misses that must not take the fast path. **Targets are expressed by text (excerpt) or by role (+ ordinal), never by block ID.** Text matching uses one normalisation function (NFC, no-break spaces → space, ’ → ', collapsed whitespace), reused by T-101.
  - **Acceptance:** `just corpus` regenerates everything, byte-identical across runs; every file opens in python-docx (except the corrupt zip); the instruction file validates against a schema; every text target matches exactly one paragraph of its document.

- [ ] **T-005b · Raw-XML fixtures** · M · Depends on: T-005a · ADR-031, ADR-041
  - Fixtures written as raw XML (lxml), carrying Word-style `w14:paraId`/`w14:textId`:
    5. title in a **text box**; 6. two-column layout section;
    9. text with **tracked changes** and comments; 10. equations and a chart (locked content);
    11. long guide (≥ 30 pages, headings, TOC field);
    15. **duplicated `w14:paraId`** inside the body and between body and header (ID repair);
    16. paragraphs mixing a hyperlink, a footnote reference, a tab, a line break, a bookmark, coloured and highlighted text, and subscript (markup tokens and style spans).
  - A real Word 97–2003 `.doc` committed as a binary fixture and renamed to `.docx`.
  - The new files go through T-005a's deterministic packaging and its "committed corpus is up to date" test (ADR-041).
  - **Acceptance:** two runs of `just corpus` produce byte-identical files; each file has its README line; every file opens in python-docx except the deliberate bad ones.

- [ ] **T-005c · Word-saved corpus variants** · S · **(human, non-blocking)** · Depends on: T-005b
  - A person opens corpus files in Microsoft Word, saves them without changes, and commits them as `*.word.docx` with a README line (Word version, date). Tests use them automatically when present; their absence never fails the build.
  - **Acceptance:** at least files 1, 2, 3, 4 and 16 have a Word-saved variant.

## E1, Document engine

- [ ] **T-101 · DocModel reader with stable IDs** · L · Depends on: T-003, T-005a, T-005b · ARCH §7.2, §7.4 · ADR-022
  - Blocks for body, table cells, headers/footers; location, style, list info, text, format summary, mixed-formatting flag.
  - IDs from `w14:paraId`. Across every part that holds paragraphs: missing and duplicated IDs (first occurrence keeps its ID) replaced deterministically (hash of part name + position, 8 hex in `00000001`–`7FFFFFFF`, counter on collision, unique across parts); same for `w14:textId`; missing `w14`/`mc` namespace declarations and `mc:Ignorable` entry added; written on the working copy.
  - Locked-content detection with reasons (fields spanning several paragraphs lock; fields inside one paragraph do not); document-level info (sections, styles, numbering, tables, warnings).
  - **Acceptance:** every corpus file loads; IDs unique and stable across save/reload; importing the same file twice gives identical IDs; duplicates in file 15 repaired; written parts declare `w14` and list it in `mc:Ignorable`; locked blocks correctly flagged on files 5, 9, 10, 11 (TOC); header/footer blocks found on 3 and 4; tests per file.

- [ ] **T-102 · Inline markup ⇄ runs** · L · Depends on: T-101 · ARCH §7.3 · ADR-021
  - Marks `**`, `*`, `__`, `^^`, `,,`; opaque tokens `⟦n⟧` for hyperlinks, footnote/endnote references, tabs, breaks, bookmarks and fields inside the paragraph (XML restored verbatim); style spans `⟦sN⟧…⟦/sN⟧` for colour, highlight, font and size differences; escaping rules.
  - Runs → markup relative to dominant formatting, plus the per-paragraph token and span tables; markup → runs cloning nearest original run properties.
  - Consider splitting in the plan: marks first, then tokens and spans.
  - **Acceptance:** hypothesis round-trip tests (text, marks, tokens, spans); mixed paragraphs from corpus files 2 and 16 survive a rewrite of identical text with no difference in normalized XML; reordering tokens moves their original XML.

- [ ] **T-103 · Model-facing serialization** · M · Depends on: T-101 · ARCH §7.5
  - Compact view (tokens and style spans as in §7.3, never their XML), outline view, section chunking, token estimate, data delimiting.
  - **Acceptance:** snapshot tests; long guide (file 11) chunked under a configurable budget; text containing fake instructions stays inside the data delimiters.

- [ ] **T-104 · Operation schemas and validator** · M · Depends on: T-101, T-102 · ARCH §7.6
  - Pydantic discriminated union for the full catalogue; JSON Schema export (used later for structured output); validator with all rules, including: `rewrite` keeps every token exactly once (order free) with balanced spans referring to existing span ids; new blocks contain no tokens or spans; `replace_in` does not touch tokens; `insert_table` after a paragraph inside a table cell rejected (ADR-033). French error messages for the teacher + technical messages for the repair loop.
  - **Acceptance:** each rule has passing and failing tests; hypothesis fuzzing never crashes the validator; schema export snapshot.

- [ ] **T-105 · Executor: text operations** · L · Depends on: T-102, T-104 · ARCH §7.7
  - `rewrite`, `replace_in`, `insert_after/before`, `delete`, `move`; transaction on a copy; exemplar cloning helper (fresh `w14:paraId`/`w14:textId` on every clone); per-operation error report.
  - **Acceptance:** golden tests on corpus files 1, 2, 3, 7, 13, 16; failure in the 3rd of 5 operations leaves the document unchanged; after any operation list, IDs are unique across all parts.

- [ ] **T-106 · Executor: formatting operations** · M · Depends on: T-105
  - `set_style` (incl. creating a style from a base), `set_font`, `set_alignment`, `set_spacing`, `set_indent`, `set_list` (bullet/number/none, formats, restart via new `w:num`).
  - **Acceptance:** golden tests; numbering restart verified in XML and by reopening; Word-compatibility check via LibreOffice is **not** required.

- [ ] **T-107 · Executor: page and structure operations** · M · Depends on: T-105
  - `set_margins`, `set_orientation` (swap page size), `page_break_before`, `insert_table`, `insert_answer_lines`, `apply_role_format` (stub until T-205 provides exemplars).
  - **Acceptance:** golden tests incl. multi-section document; `insert_table` after a paragraph inside a table cell is rejected with the French message from T-104 (ADR-033).

- [ ] **T-108 · Atomic save, integrity check, no-op round trip** · M · Depends on: T-105
  - Temp write + fsync + reopen + zip check + `os.replace`; normalized-XML comparison utility.
  - **Acceptance:** no-op round trip equivalent on all corpus files; simulated crash during save leaves the previous version intact; Windows path edge cases (spaces, accents, long paths) tested.

- [ ] **T-109 · Proposal diff** · S · Depends on: T-105
  - Block-level diff (added/removed/changed/format-only) + word-level text diff; JSON shape for the UI.
  - **Acceptance:** unit tests on crafted pairs; diff of a no-op is empty.

- [ ] **T-110 · Versions and workspaces** · M · Depends on: T-004, T-108 · ARCH §7.9
  - Import from uploaded bytes (write `original.docx`, assign IDs), versions table, head pointer, undo/redo, export copy to a given path (overwriting an existing file only with an explicit `overwrite` flag, ADR-032), retention policy job.
  - **Acceptance:** integration tests of the full lifecycle; original file hash unchanged after any sequence of operations; export refuses to overwrite without the flag.

## E2, Template learning

- [ ] **T-201 · Container extraction** · M · Depends on: T-101 · ARCH §8.2
  - Copy styles, numbering, theme, settings, sections, headers/footers (with images and RTL text); empty the body keeping the final section properties.
  - **Acceptance:** container of corpus files 1, 3, 4 opens, shows the same header/footer and page setup, contains no body text.

- [ ] **T-202 · Role taxonomy and rule-based classifier** · L · Depends on: T-101 · ARCH §8.3, §8.4
  - Feature extraction; French rules in `config/rules.fr.yaml`; scoring with confidence; deterministic output.
  - **Acceptance:** labelled ground truth for ≥ 6 corpus files (stored next to them); report per role; ≥ 80 % accuracy rules-only on clean files, measured and printed by a test.

- [ ] **T-203 · LLM-assisted classification** · M · Depends on: T-202, T-304
  - One batched call (`classify` chain) for blocks under the threshold; schema-validated; merges with rule results; uses teacher corrections as few-shots when available.
  - **Acceptance:** with FakeLLM, low-confidence blocks are sent in one call and merged; prompt snapshot test; live eval documented in T-207.

- [ ] **T-204 · Template profile builder** · M · Depends on: T-201, T-202
  - `profile.json` schema v1 (ARCH §8.6), exemplar selection per role (most representative paragraph), structure inference, conventions detection (tu/vous, points format, section label, total), short excerpts.
  - **Acceptance:** profiles for corpus files 1, 2, 7, 8, 13 match expected snapshots; schema versioning test.

- [ ] **T-205 · Renderer by exemplar cloning** · L · Depends on: T-204, T-106 · ARCH §8.7
  - Role-tagged content → document from container; numbering restarts per section; answer lines; tables; missing styles/numbering copied; fallback chain for unknown roles; fresh paragraph IDs on every clone; completes `apply_role_format`.
  - **Acceptance:** rendering the same content with templates from files 1 and 2 gives two documents that each match their source's look (golden tests on formatting properties).

- [ ] **T-206 · Template library and built-in templates** · M · Depends on: T-205, T-004
  - CRUD, storage layout, index table, name/description, source hash, created/updated; two built-in templates generated through the pipeline at build time.
  - **Acceptance:** integration tests; built-ins available on a fresh install.

- [ ] **T-207 · Template learning evaluation** · S · Depends on: T-203, T-204
  - `just eval-templates`: accuracy per role (rules only, rules + FakeLLM replay; optional live run), confusion matrix, saved report in `docs/reports/`.
  - **Acceptance:** report generated; target ≥ 90 % with LLM pass on the synthetic corpus, or gaps documented with follow-up tickets.

- [ ] **T-208 · Role classification on import** · M · Depends on: T-202, T-203, T-110 · ARCH §8.4 · ADR-023
  - Rules-only classification (zero AI calls) of every imported document and of each new version; role map cached per version; exposed by the documents service for `GET /documents/{id}`.
  - On-demand LLM pass for low-confidence blocks (one batched `classify` call through T-203), result cached on the version; never triggered automatically.
  - **Acceptance:** import makes no LLM call (asserted with FakeLLM); cached roles reused on reload; on-demand pass merges results and is cached; roles on corpus files 1 and 2 reach the T-202 accuracy level.

## E3, LLM gateway

- [ ] **T-301 · Provider configuration and key storage** · M · Depends on: T-003
  - `models.yaml` schema (providers with `quota_reset_tz`, models, limits, capabilities, task chains `route_plan`, `answer`, `write_fr`, `classify`, `stt`) with user override merge; `keyring` storage; key test with an authenticated `GET /models`, or the provider's equivalent zero-quota authenticated endpoint where the model list is public (ADR-027).
  - **Acceptance:** schema validation errors are clear; keys never appear in logs (tested); keyring mocked in tests; key test consumes no quota (no chat call).

- [ ] **T-302 · Router with fallback chains** · L · Depends on: T-301, T-305 · ARCH §9.3
  - OpenAI-compatible client over `httpx`; per-provider quirks isolated in small adapters; timeouts; error classification (rate limit minute/day, server, timeout, auth, invalid output, offline); cooldowns from headers or backoff, daily-limit cooldowns until the provider's next reset in its `quota_reset_tz`; returns result + model used + timings.
  - Defines the **quota interface** the router consults before each call, with a permissive stub; T-303 implements it.
  - **Acceptance:** tests with a mock transport for each error class: correct next model, correct cooldown, offline mode without cooldowns; router skips a model the quota interface refuses; no model names in code (grep test).

- [ ] **T-303 · Quota tracker** · M · Depends on: T-302, T-004
  - SQLite implementation of the quota interface from T-302: counters per model per minute/day, day windows in each provider's `quota_reset_tz`, header reconciliation, pre-call checks, `/quota` data shape.
  - **Acceptance:** time-controlled tests (injected clock) for minute and day windows and the daily reset in UTC and in `America/Los_Angeles` (including a DST change).

- [ ] **T-304 · Structured output layer** · M · Depends on: T-302
  - json_schema → json_object → text modes by capability; tolerant parsing; Pydantic validation; one repair retry with the error; then fallback.
  - **Acceptance:** tests for fenced JSON, trailing commas, wrong types, missing fields, and the retry path.

- [ ] **T-305 · FakeLLM and recorded fixtures** · S · Depends on: T-003
  - Scripted fake (queue or keyed by task + prompt hash), recorder for `eval-live` runs to create replay fixtures, guard that fails any test attempting real network.
  - Backend startup flag `--fake-llm <fixtures>` replacing every provider with the FakeLLM, for end-to-end tests; refused with a startup error in packaged (frozen) builds (ADR-034).
  - **Acceptance:** used by T-302 tests; network guard proven by a test; `--fake-llm` works in development and is refused when frozen (tested by simulating a frozen build).

- [ ] **T-306 · Verify current free models and fill defaults** · S · Depends on: T-301
  - Check each provider's current free models, limits, daily reset time zone, OpenAI-compatible endpoint behaviour, JSON support and zero-quota key-check endpoint from official pages/consoles; write `docs/PROVIDERS.md` (dated, with links) and `models.default.yaml` with chains `route_plan`, `answer`, `write_fr`, `classify`, `stt`; contract tests with recorded responses.
  - **Acceptance:** at least 2 models per task chain; a live smoke script succeeds with real keys provided by the user (manual).

## E4, Agent

- [ ] **T-401 · Fast path rules** · M · Depends on: T-104, T-202, T-208
  - French patterns → operations (bold/italic/underline, font name/size, alignment, spacing, margins, orientation, lists) targeted at the selection or at a role (role map from import); ambiguity → no match.
  - **Acceptance:** all fast-path instructions in `instructions.yaml` matched with correct operations; no false matches on the others.

- [ ] **T-402 · Graph skeleton, state and checkpointer** · M · Depends on: T-305, T-004, T-006 · ARCH §10 · ADR-028, ADR-029
  - LangGraph state (incl. `run_id`, `base_version_id`), nodes as stubs, SQLite checkpointer in a separate `db/checkpoints.sqlite` in WAL mode, conversation memory (last N turns, older turns truncated without AI), correlation IDs, event emission interface.
  - The agent package is lazy-imported on the first instruction, never at startup.
  - Re-run `just measure` (T-006) with the agent loaded and record the result.
  - Run status persisted (`running`, `awaiting_decision`, `done`, `error`, `cancelled`, `interrupted`); on backend startup every run still `running` becomes `interrupted`.
  - **Acceptance:** a stubbed run goes from instruction to a pending proposal and resumes after a simulated app restart; a run left `running` by a simulated crash is `interrupted` after restart while an `awaiting_decision` run is not; a test proves the agent is not imported at startup; measurement report updated. If LangGraph adds more than 40 MB idle RSS or more than 1.5 s cold start, stop and propose the replacement ADR and tickets (ADR-029).

- [ ] **T-403 · Edit planning (route + plan)** · L · Depends on: T-402, T-103, T-304, T-401, T-202, T-208
  - Prompt `route_plan.md` (French, few-shots) on the `route_plan` chain, target resolution (selection → role map from import → model), questions answered directly by `route_plan` when the compact view is enough, otherwise by the `answer` node on the `answer` chain with a larger part of the document.
  - **Acceptance:** `just eval` with FakeLLM replay passes for edit instructions and questions; average ≤ 1.3 LLM calls per edit instruction; questions answerable from the compact view use 1 call, the others 2.

- [ ] **T-404 · Create flow (outline → content)** · L · Depends on: T-403, T-205, T-206
  - Outline node + interrupt with editable outline (records `base_version_id`); `write_content` per section or whole doc by context budget, using profile conventions and excerpts; renderer to a new document.
  - **Acceptance:** creating a document from built-in and learned templates works end to end with FakeLLM; outline edits are respected.

- [ ] **T-405 · Validation, repair and proposal assembly** · M · Depends on: T-403, T-109
  - Validator errors → one repair call → proposal (executor on copy, diff, reasons, `base_version_id`) → interrupt; accept all / subset / reject; accepting when the head has moved fails with `proposal_stale` (ADR-025).
  - **Acceptance:** invalid first answer repaired in tests; subset acceptance re-validates and applies only chosen ops; stale proposal refused and nothing applied.

- [ ] **T-406 · Progress events** · S · Depends on: T-403, T-404, T-405
  - Event types from ARCH §10.3 emitted by nodes, with increasing event ids; French labels.
  - **Acceptance:** event sequence snapshot per flow (edit, question, create).

- [ ] **T-407 · Agent evaluation harness** · M · Depends on: T-403, T-404
  - `just eval` (replay) and `just eval-live`: correctness checks from `instructions.yaml` (targets resolved by text or role), calls per instruction, latency, fallbacks used; report in `docs/reports/`.
  - **Acceptance:** report generated; live run done once with the user's keys and results reviewed.

## E5, API

- [ ] **T-501 · Documents API** · M · Depends on: T-110, T-101, T-208
  - Routes from ARCH §12 for documents, files, versions, undo/redo, export: import by **multipart upload only** with size and zip-bomb limits (ADR-032); `GET /documents/{id}` with the role map of the head version; `POST /documents/{id}/roles/refine`; export to a path with the `overwrite` flag.
  - **Acceptance:** integration tests incl. limits, corrupt files and `.doc` renamed to `.docx` (French error codes); export refuses to overwrite without the flag.

- [ ] **T-502 · Instructions, proposals and outlines API (SSE)** · M · Depends on: T-405, T-406, T-501, T-404 · ADR-024, ADR-025
  - `POST /conversations/{id}/instructions` → `{run_id}`; `GET /runs/{id}/events` (SSE, event ids, replay from `Last-Event-ID`); resumes after accept/reject/approve emit on the same run; `POST /runs/{id}/cancel`; accept/reject/subset; outline approval; 409 `run_in_progress` and `proposal_stale`.
  - **Acceptance:** integration tests for each flow with FakeLLM; reconnecting with `Last-Event-ID` replays missed events; a client disconnect does not cancel the run; cancel stops it cleanly; second run on the same document → 409; accept after the head moved → 409; after a simulated backend restart, a run that was streaming is `interrupted`, its event stream ends with `run_interrupted`, and a new run on the same document is accepted.

- [ ] **T-503 · Templates API** · S · Depends on: T-206, T-203
  - Learn, review data (blocks + roles + colours), role corrections, save, list, delete.
  - **Acceptance:** integration tests.

- [ ] **T-504 · Settings, keys, quota, diagnostics API + TS client generation** · M · Depends on: T-301, T-303
  - Routes (key test uses the zero-quota check from T-301); diagnostics zip redaction; `just gen-api` producing the frontend client; CI check that the generated client is up to date.
  - **Acceptance:** tests; redaction verified on a zip containing fake keys and document text.

## E6, Interface

- [ ] **T-600 · Spike: docx-preview block mapping** · M · Depends on: T-101 · Milestone M2
  - Prototype (frontend scaffold from T-001; corpus files and DocModel JSON served by a throwaway script, no API needed): render corpus files with docx-preview, map rendered paragraphs to block IDs (order + normalized text), click-select and highlight; measure mapping accuracy per file.
  - Experiment: inject bookmarks named after each `paraId` into a preview copy only (never into versions) and check whether docx-preview renders them as anchors usable for exact mapping.
  - Decide keep vs fallback editing view (ARCH §13.2). Write an ADR with the result; if the fallback is chosen, T-611 is activated.
  - **Acceptance:** accuracy table for all corpus files, with and without bookmark anchors; ADR written; throwaway code removed or moved into T-604.

- [ ] **T-601 · App shell and design system** · M · Depends on: T-001
  - Routing, layout, Tailwind + shadcn/ui, French i18n setup, theme (calm, readable, large touch targets), error boundaries, connection to backend via Tauri command (dev fallback: env vars).
  - **Acceptance:** screens navigable with placeholders; vitest for i18n completeness (no missing keys).

- [ ] **T-602 · First-launch wizard** · M · Depends on: T-601, T-504
  - Welcome, keys step with links and "Tester", training-use disclosure, optional first template, finish.
  - **Acceptance:** Playwright flow with mocked key test; cannot finish without one valid provider.

- [ ] **T-603 · Home screen** · S · Depends on: T-601, T-501
  - Recent documents, open via the WebView file picker + upload (same code path in Tauri, browser dev and tests), new document entry, templates entry.
  - **Acceptance:** component and E2E tests.

- [ ] **T-604 · Editor: page view with selection** · L · Depends on: T-600, T-603 (and T-611 if activated)
  - docx-preview view (or the T-611 editing view), block selection (click, shift-click), role colours toggle with "Affiner les rôles", highlight of proposal targets, zoom.
  - **Acceptance:** E2E: select two blocks, selection IDs sent with the instruction.

- [ ] **T-605 · Editor: chat panel** · M · Depends on: T-604, T-502
  - Messages, input, Ctrl+Entrée, shortcut chips (configurable prompts), progress steps from the run stream read with `fetch` streaming and resumed with `Last-Event-ID` (never re-sending the instruction), model badge, French errors with retry, `run_in_progress` handling, interrupted run shown as "La dernière demande a été interrompue." with a "Relancer" button.
  - **Acceptance:** E2E against the backend started with `--fake-llm` for an edit instruction and a question; a dropped stream resumes without a duplicate instruction; an interrupted run shows the message and "Relancer" starts a new run.

- [ ] **T-606 · Editor: proposals, versions, export** · M · Depends on: T-605
  - Proposal panel (reasons, word diff, accept all/subset/reject, French message and relaunch on `proposal_stale`), versions timeline, undo/redo, export via the native save dialog (French confirmation before overwriting), quota indicator.
  - **Acceptance:** E2E: propose → accept subset → undo → redo → export; accepting a stale proposal shows the French message.

- [ ] **T-607 · Create flow UI** · M · Depends on: T-606, T-404
  - Template picker, description form or free text, outline editor (reorder, rename, delete), generation progress, open result in editor.
  - **Acceptance:** E2E create flow with FakeLLM.

- [ ] **T-608 · Template learning wizard and library** · M · Depends on: T-604, T-503
  - Choose file → analysis → role review (colours, legend, click to change role) → name → save; library list, rename, delete.
  - **Acceptance:** E2E: learn template from corpus file 2, correct one role, use it in the create flow.

- [ ] **T-609 · Settings screen** · S · Depends on: T-602
  - Keys, advanced model chains editor (with validation), quota dashboard, voice settings (Groq), retention, diagnostics export, about.
  - **Acceptance:** component tests; invalid chain config rejected with a French message.

- [ ] **T-610 · States, accessibility and polish** · M · Depends on: T-606, T-607, T-608
  - Empty, loading, offline, quota-exhausted, backend-restarting states; keyboard navigation; focus management; 125–150 % scaling check; consistent French copy review.
  - **Acceptance:** axe checks in Playwright with no serious violations; manual checklist done.

- [ ] **T-611 · Fallback editing view** · L · **Conditional:** only if the T-600 ADR chooses the fallback · Depends on: T-600, T-603 · ARCH §13.2
  - Editing view rendered from the DocModel by React components (approximate formatting, exact block IDs) with block selection; the docx-preview page view stays available read-only for visual checking.
  - **Acceptance:** the T-604 selection E2E passes against this view.

## E7, Voice

- [ ] **T-701 · STT service and Groq provider** · S · Depends on: T-302, T-303
  - STT interface, Groq Whisper via the gateway chain `stt`, `POST /stt` (≤ 60 s, French), errors.
  - **Acceptance:** tests with recorded responses; quota counted.

- [ ] **T-702 · Microphone UI** · M · Depends on: T-701, T-605
  - Push-to-talk button and key, level meter, permission handling in WebView2, transcript inserted for editing before sending.
  - **Acceptance:** component tests with a mocked MediaRecorder; manual test inside Tauri on Windows.

## E8, Desktop and release

- [ ] **T-801 · Tauri shell and sidecar lifecycle** · L · Depends on: T-003, T-601, T-006 · ARCH §4
  - Builds on the T-006 skeleton: port + token handshake, health wait, crash restart once, graceful shutdown + process-tree kill, single instance, window state, native save dialog, CSP and minimal capabilities.
  - Tauri passes its app data directory to the backend at startup (CLI argument), so all user data lives under one folder; update ARCHITECTURE §4 and §7.9 accordingly (open point of ADR-036).
  - **Note (ADR-038):** the port handshake is the backend's stdout ready line (`--port 0`, read `{"event":"ready","port":…,"version":…}` with a timeout; the version can be checked against the app's); the backend already accepts `--data-dir` for the item above. Keep reading (or draining) the child's stdout and stderr so the pipes never fill up.
  - **Note (ADR-040):** exit code 3 means the database cannot be opened or migrated. The French error screen for it offers "Réinitialiser l'historique", which moves `assistant.sqlite` and its `-wal`/`-shm` files to `db/corrupt/<timestamp>/` without deleting anything, then restarts the backend.
  - **Acceptance:** manual + scripted tests on Windows: kill backend → restarts; close window → no orphan process.

- [ ] **T-802 · Backend packaging (PyInstaller onedir)** · M · Depends on: T-801
  - Spec file, hidden imports, data files (prompts, config, built-in templates, migrations), no UPX, size report, startup time measurement (via `just measure`).
  - **Acceptance:** packaged backend starts and passes `/health` on a clean Windows runner; size and start time recorded against budgets.

- [ ] **T-803 · Windows installer** · M · Depends on: T-802
  - Tauri NSIS bundle, per-user, French, WebView2 bootstrapper, icons, metadata, uninstall keeps or removes user data (asks).
  - **Acceptance:** install/uninstall on a clean Windows VM without admin rights.

- [ ] **T-804 · Release workflow and auto-update** · M · Depends on: T-803, T-002
  - Merged with former T-805.
  - Tag → build on windows-latest → artifacts + updater manifest → draft GitHub release with changelog from commits.
  - Updater key pair (private key in GitHub secrets), update check on start (non-blocking), French prompt.
  - **Acceptance:** a test tag produces a downloadable installer; update from version N to N+1 via a test release.

- T-805 · *Merged into T-804.*

- [ ] **T-806 · Packaged smoke test and low-end QA** · M · Depends on: T-804
  - PowerShell smoke test in CI (silent install, launch, health, upload a corpus doc via the API, exit, uninstall); `docs/QA_CHECKLIST.md`; manual run on a 4 GB RAM Windows VM with measurements vs budgets.
  - **Acceptance:** smoke test green in CI; QA report with numbers in `docs/reports/`.

- [ ] **T-807 · User guide (French)** · S · Depends on: T-806
  - `docs/user-guide-fr.md` (+ PDF export): installation with the SmartScreen step, getting free API keys (with links), first document, learning a template, voice, troubleshooting, exporting diagnostics.
  - **Acceptance:** a non-technical tester follows it from zero to a first edited document.

## Later (post-v1)

- [ ] **T-703 · Optional local STT** · M · Depends on: T-701, T-609 · ADR-030
  - Moved out of v1: the `faster-whisper`/`ctranslate2` runtime would break the installer size budget. Revisit as a separately downloaded component.
  - Hardware check (RAM, AVX2), on-demand download of runtime and model with progress and checksum, `faster-whisper` `base` int8, lazy import; off by default.
  - **Acceptance:** disabled path adds no startup cost (measured); enabled path transcribes a French sample in tests marked `slow`; installer size budget still met.
