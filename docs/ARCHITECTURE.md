# Assistant Prof: Architecture

> Status: **v1.0, agreed design baseline** (15 Oct 2026).
> Any change to this document goes through a new entry in `docs/DECISIONS.md`.
> Code, comments and docs are in **English**. Everything the teacher sees (UI, messages, prompts to the models) is in **French**.

---

## 1. Product

### 1.1 Vision
A Windows desktop application that combines **Word documents + AI agents** to help French teachers prepare exams, exercise sheets and guides faster. The teacher talks or types instructions; the system proposes changes to the document; the teacher accepts or rejects them.

The system **learns each teacher's own document layouts** (templates) from the documents they provide, so it works for any teacher and any document, not only for layouts we designed.

### 1.2 Users
- French teachers (primary and secondary), non-technical.
- Windows 10/11 laptops, possibly old and low-powered (unknown RAM; design for 4 GB minimum, 8 GB typical).
- Documents are **not confidential**: exams, exercises, guides, answer keys.

### 1.3 Use cases (v1)

| ID | Use case | Summary |
|---|---|---|
| UC1 | Edit an existing document | Open a .docx, give an instruction (formatting, rewording, generation), review the proposal, accept or reject. |
| UC2 | Create a new document | Pick a template, describe the document ("contrôle de 1 h sur le passé composé, 7e, 4 exercices, barème sur 20"), validate the outline, get the full document. |
| UC3 | Learn a template | Provide one of their own documents; the system extracts its layout and conventions; the teacher checks the detected roles; the template is saved in their library. |
| UC4 | Voice instruction | Push-to-talk, see and edit the transcript, send it as an instruction. |
| UC5 | History | Undo/redo, see versions, export the current version as .docx anywhere on disk. |

### 1.4 Instruction types the agent must handle
- **Formatting:** styles, headings, fonts, sizes, bold/italic/underline, alignment, spacing, indentation, lists, margins, orientation, page breaks, tables.
- **Rewording:** rewrite, simplify, enrich, correct spelling/grammar, change register (tu/vous), adapt to a class level.
- **Generation:** exercises, multiple-choice questions, dictations, fill-in-the-blanks, reading-comprehension questions, answer keys, marking rubrics, instructions, short texts.
- **Questions about the document** ("combien de points au total ?") answered in chat without changing the document.

### 1.5 Non-goals for v1
Text boxes, equations, SmartArt, charts and floating images are **never modified** (kept untouched). No tracked changes output. No .doc (Word 97–2003) or PDF input as editable documents. No Word add-in. No multi-user, no cloud sync, no accounts.

---

## 2. Constraints and quality attributes

| Attribute | Requirement |
|---|---|
| **Cost** | Strictly **0 $**: free API tiers only, no paid services, no code-signing certificate, free CI minutes. |
| **Platform** | Windows 10 (22H2+) and 11, x64. Developer machines may be Windows or Linux. |
| **Hardware** | Must run on 4 GB RAM. Budgets: backend idle RSS < 250 MB, whole app < 450 MB; cold start < 6 s on a 4-core 2015-era CPU. No local LLM. |
| **Data safety** | The teacher's original file is **never modified**. Every write is atomic. No data loss on crash or power cut. |
| **Reliability** | The AI never writes the file. It proposes operations from a closed catalogue; deterministic code validates and applies them. |
| **Availability of AI** | Free quotas run out and free models disappear. The app must degrade gracefully: automatic fallback across providers, clear French message when everything is exhausted, all non-AI features keep working offline. |
| **Latency** | Simple formatting instruction (rule path): < 1 s. AI edit instruction: p50 < 10 s, p95 < 30 s. Progress is always visible. |
| **Usability** | Non-technical users: no terminal, one installer, guided setup, everything in French, keyboard accessible, readable at 125–150 % Windows scaling. |
| **Security** | API keys in Windows Credential Manager. Backend reachable only from the app (localhost + session token). Model output is never executed. |
| **Maintainability** | Senior-level codebase: strict typing, high test coverage on the core, CI on Windows, documented decisions, no hard-coded model names. |
| **Privacy** | No telemetry. Logs stay local; the teacher can export a diagnostic zip (keys and document text redacted) to send to support. |

---

## 3. System context

```
                ┌──────────────────────────────────────────────┐
  Teacher ────► │  Assistant Prof (Windows desktop app)        │
  (mouse,       │                                              │
   keyboard,    │  .docx files on disk  ◄──── open / export    │
   microphone)  └───────────────┬──────────────────────────────┘
                                │ HTTPS (only for AI and voice)
          ┌─────────────────────┼─────────────────────────────┐
          ▼                     ▼                             ▼
   Gemini API (free)     Groq API (free:            Mistral API (free)
                         LLM + Whisper STT)
                                                    OpenRouter :free (last resort)
          GitHub Releases (update checks, optional)
```

---

## 4. Containers and process model

```
┌──────────────────────── Assistant Prof.exe (Tauri 2) ─────────────────────────┐
│  Rust shell (thin)                                                            │
│   ├─ starts / stops the backend sidecar, health-check handshake               │
│   ├─ native dialogs (open/save), single instance, window state, updater       │
│   └─ WebView2 window ──► React + Vite + TypeScript frontend                   │
│                              │  HTTP + SSE to 127.0.0.1:<random port>         │
│                              │  header: X-Session-Token: <random token>       │
│  Python backend sidecar (PyInstaller onedir, FastAPI + Uvicorn)               │
│   ├─ document engine  ├─ template learning  ├─ agent (LangGraph)              │
│   ├─ LLM gateway      ├─ voice (STT)        ├─ versions + SQLite              │
└───────────────────────────────────────────────────────────────────────────────┘
            Data: %APPDATA%\AssistantProf\  (workspaces, templates, db, logs)
```

**Sidecar lifecycle**
1. Tauri picks a free port and generates a 32-byte random session token.
2. Tauri spawns the backend with `--port` and the token in an environment variable.
3. The backend binds **127.0.0.1 only** and rejects any request without the token, including `/health`.
4. Tauri polls `/health` (timeout 20 s, then a French error screen with "Réessayer" and "Exporter le diagnostic").
5. The frontend gets `{port, token}` through a Tauri command, never from the URL.
6. On window close, Tauri asks the backend to shut down gracefully (`POST /shutdown`), then kills the process tree after 3 s.
7. Single-instance plugin: a second launch focuses the existing window.
8. If the backend crashes, Tauri restarts it once and shows a non-blocking notice; the second crash shows the error screen.

---

## 5. Repository layout

```
assistant-prof/
├─ CLAUDE.md                     working rules for Claude Code
├─ README.md
├─ justfile                      one entry point for all commands
├─ docs/
│  ├─ ARCHITECTURE.md  DECISIONS.md  TICKETS.md
│  ├─ PROVIDERS.md               current free models and limits (dated)
│  └─ user-guide-fr.md
├─ backend/
│  ├─ pyproject.toml  uv.lock
│  ├─ src/assistant_prof/
│  │  ├─ core/          config, paths, logging, errors, ids, clock
│  │  ├─ docmodel/      reader, blocks, inline markup, serializer for LLM
│  │  ├─ operations/    operation schemas + validator
│  │  ├─ executor/      apply operations, cloning, numbering, atomic save, diff
│  │  ├─ templates/     container extraction, role classifier, profile, renderer, library
│  │  ├─ llm/           gateway, providers, router, quota, structured output, fake
│  │  ├─ agent/         graph, nodes, state, fast path, prompts loader
│  │  ├─ voice/         STT interface, Groq provider, optional local provider
│  │  ├─ versions/      workspaces, history, undo/redo, export
│  │  ├─ persistence/   SQLAlchemy models, repositories, Alembic migrations
│  │  └─ api/           FastAPI app factory, routers, auth, SSE, error handlers
│  ├─ prompts/          French prompt files (*.md) with few-shot examples
│  ├─ config/           models.default.yaml, rules.fr.yaml
│  └─ tests/            unit/, integration/, golden/, eval/, fixtures/
├─ corpus/
│  ├─ generator/        scripts that build the synthetic test corpus
│  ├─ docs/             generated + real .docx (real ones git-ignored if needed)
│  └─ instructions.yaml test instructions with expected outcomes
├─ frontend/
│  ├─ package.json  vite.config.ts  tsconfig.json
│  └─ src/  app/ pages/ features/ components/ api/ i18n/ lib/
└─ desktop/
   └─ src-tauri/        Rust shell, tauri.conf.json, capabilities, icons
```

---

## 6. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Desktop shell | **Tauri 2** | WebView2 (bundled bootstrapper), plugins: shell, dialog, single-instance, window-state, updater, process. |
| Frontend | **React + Vite + TypeScript (strict)** | Tailwind CSS + shadcn/ui (Radix, accessible), TanStack Query (server state), Zustand (UI state), React Router, `docx-preview` for the page view. |
| API client | `openapi-typescript` + `openapi-fetch` | Types generated from the backend OpenAPI schema; no hand-written API types. |
| Backend | **Python 3.12**, FastAPI, Uvicorn, Pydantic v2 | `uv` for environments and lockfile. |
| Word | `python-docx` + `lxml` | Direct XML where python-docx has no API (paraId, numbering, cloning). |
| Agent | **LangGraph** | SQLite checkpointer, interrupts for human approval. |
| LLM access | **In-house thin gateway over OpenAI-compatible endpoints** (`httpx`) | See ADR-015. Gemini, Groq, Mistral and OpenRouter all expose OpenAI-compatible chat endpoints. |
| Persistence | SQLite + SQLAlchemy 2 + Alembic | One file in the data directory. |
| Secrets | `keyring` (Windows Credential Manager) | Never in files or logs. |
| Logging | `structlog` → JSON lines, rotating files | Correlation ID per instruction. |
| STT | Groq Whisper (free); optional `faster-whisper` `base` int8 | Local STT off by default (hardware unknown). |
| Packaging | PyInstaller **onedir** (no UPX) + Tauri NSIS installer, per-user | No admin rights needed. |
| Quality | ruff, mypy `--strict`, pytest (+ hypothesis), eslint, prettier, tsc, vitest, Playwright, cargo clippy | pre-commit + CI. |
| CI/CD | GitHub Actions (ubuntu + windows runners) | Release on tag builds the Windows installer. |

Library versions: latest stable at implementation time, pinned in lockfiles.

---

## 7. Document engine

### 7.1 Core principle
**The AI never touches the file.** Pipeline for every change:

```
.docx ─► DocModel ─► (agent) ─► Operation list (JSON) ─► Validator ─► Executor (on a copy)
                                                                         │
                     teacher accepts ◄── Proposal (diff + reasons) ◄─────┘
                          │
                          ▼
                  new version vNNN.docx  (original never modified)
```

### 7.2 DocModel
- Built from the .docx by `docmodel.reader`.
- A **block** is a paragraph wherever it lives: body, table cell, header, footer. Each block has:
  - `id`: **stable ID based on `w14:paraId`**. Word writes this attribute on every paragraph since Word 2010. If missing (files from LibreOffice or generators), the reader assigns unique values (8 hex digits, < `0x80000000`) and writes them on the working copy, so IDs survive save/reload and appear in every version.
  - `location`: `body` | `table(t, r, c)` | `header(section, type)` | `footer(...)`.
  - `style_id`, `style_name`, `role` (if known, see §8), `list` info (numId, level), `text`.
  - `markup`: text with inline marks (§7.3).
  - `format_summary`: dominant font/size/bold/italic/alignment; `mixed_formatting: bool`.
  - `locked: bool` + `lock_reason` (see 7.4).
- Document-level info: sections (page size, orientation, margins, columns), styles available, numbering definitions, tables (dimensions), images count, warnings.

### 7.3 Inline markup
A small, strict markup lets the model rewrite paragraphs that mix formatting:
`**gras**`, `*italique*`, `__souligné__`, `^^exposant^^`. Anything else is literal text.
- Reader: runs → markup (only for marks that differ from the paragraph's dominant formatting).
- Executor: markup → runs, each run cloned from the closest original run formatting (font, size, color), with the mark applied.
- Round-trip property (tested with hypothesis): `parse(serialize(runs))` keeps text and marks.

### 7.4 Locked content (never modified)
Paragraphs containing or inside: text boxes (`w:txbxContent`), drawings/charts/SmartArt, equations (`m:oMath`), fields other than simple page numbers, content controls (`w:sdt`), tracked changes (`w:ins`/`w:del`), comments ranges. They appear in the DocModel with `locked=true`; the validator rejects any operation targeting them. If a document contains tracked changes, the app warns and suggests accepting them in Word first.

### 7.5 Serialization for the model
Compact, token-efficient view:
```
[p:1A2B3C4D|titre|Title] Contrôle de grammaire
[p:5E6F7A8B|consigne|Normal] Conjuguez les verbes au passé composé. (**4 pts**)
[t1 r2 c1 p:...|question|List Paragraph] Hier, nous (aller) au cinéma.
```
- Long documents are split by sections/headings; the agent receives only the relevant part plus an outline of the rest.
- Token estimate per view (character-based heuristic, calibrated in tests) to respect each model's context.
- Document text is wrapped as **data** in prompts (delimited), never as instructions.

### 7.6 Operation catalogue (v1)
All operations are Pydantic models in a discriminated union (`op` field), each with `op_id` and a French `reason` shown to the teacher.

| Group | Operation | Parameters (main) |
|---|---|---|
| Text | `rewrite` | `id`, `markup` |
| | `replace_in` | `id`, `find`, `replace`, `all` |
| | `insert_after` | `id`, `blocks: [{role?, style?, markup, list?}]` |
| | `insert_before` | same |
| | `delete` | `ids` |
| | `move` | `ids`, `after_id` |
| Format | `set_style` | `ids`, `style` (existing or created from a base) |
| | `set_font` | `ids`, `name?`, `size_pt?`, `bold?`, `italic?`, `underline?`, `color?` |
| | `set_alignment` | `ids`, `left/center/right/justify` |
| | `set_spacing` | `ids`, `before_pt?`, `after_pt?`, `line?` |
| | `set_indent` | `ids`, `left_cm?`, `first_line_cm?` |
| | `set_list` | `ids`, `type: bullet/number/none`, `format?` (1., a), I., …), `restart?` |
| Page | `set_margins` | `section`, `top/bottom/left/right_cm` |
| | `set_orientation` | `section`, `portrait/landscape` |
| | `page_break_before` | `id` |
| Structure | `insert_table` | `after_id`, `rows`, `cols`, `cells`, `header_row`, `style?` |
| | `insert_answer_lines` | `after_id`, `count`, `kind: dots/underscores/blank_lines` |
| | `apply_role_format` | `ids`, `role` (formats blocks like the template exemplar for that role) |

Validator rules (pure functions, unit-tested): IDs exist and are not locked; no duplicated targets across conflicting ops; numeric ranges (font 6–72 pt, margins 0–5 cm…); style exists or is creatable; table size ≤ 30×10; total inserted text ≤ limit; operations are ordered and their combined effect is well-defined (e.g. no edit after delete of the same block).

### 7.7 Executor
- Applies operations to a **copy** of the current version, inside a transaction: if any operation fails, nothing is kept and the error is reported per operation.
- **Formatting preservation:** `rewrite` keeps paragraph properties (`pPr`) and rebuilds runs from markup using the original runs' properties.
- **Exemplar cloning:** new paragraphs are created by deep-copying an exemplar paragraph (from the document itself or from the template profile), removing its runs, then inserting new runs with the exemplar's first-run properties. This is how generated content matches the teacher's layout exactly.
- **Numbering:** new lists reuse the exemplar's `abstractNum`; `restart` creates a new `w:num` pointing to it with a level override, so "Exercice 2" restarts at 1).
- **Atomic save:** write to `*.tmp` in the same folder, `fsync`, reopen with python-docx and check zip integrity, then `os.replace`.
- **No-op round trip guarantee:** opening and saving without operations must produce a document equivalent to the original (normalized XML comparison on the whole corpus).

### 7.8 Proposals and diff
A proposal = operations + preview file + diff:
- Block-level diff: added / removed / changed / format-only.
- Word-level text diff for changed blocks (`difflib`), rendered in the UI in green/red.
- The teacher can accept all, reject all, or **accept per operation** (the executor re-applies only the selected subset and re-validates).

### 7.9 Versions and workspaces
```
%APPDATA%\AssistantProf\
├─ workspaces\<doc-uuid>\
│  ├─ original.docx        imported copy, read-only, never modified
│  ├─ versions\v001.docx … vNNN.docx
│  └─ proposals\<proposal-id>.docx   (temporary, cleaned up)
├─ templates\<template-uuid>\ container.docx, profile.json, thumbnail.png
├─ db\assistant.sqlite
└─ logs\
```
- History table: version id, parent id, instruction text, operations JSON, model used, timestamp.
- Undo/redo moves the head pointer; nothing is deleted. Export copies the head version to a path chosen in a native save dialog. Optional "replace the original file" export asks for explicit confirmation.
- Cleanup policy: keep all versions of the last 30 days, then the last 20 versions per document (configurable).

---

## 8. Template learning

### 8.1 Goal
Turn **any** teacher document into a reusable template that reproduces its look (styles, header, page setup) and its conventions (structure, wording), so that generated documents look like the teacher made them.

### 8.2 Pipeline

```
teacher .docx
   │ 1. container extraction (no AI)
   ▼
container.docx = styles + numbering + theme + sections + header/footer, empty body
   │ 2. role classification: rules (confidence) → 1 batched LLM call for low-confidence blocks
   ▼
role map   ──► 3. teacher review screen (colour per role, click to correct, name the template)
   │
   ▼ 4. profile builder
profile.json = exemplars per role + structure + conventions + short real excerpts
```

### 8.3 Role taxonomy (v1)
`titre`, `sous_titre`, `champ_entete` (Nom / Classe / Date / Note), `info_epreuve` (durée, matière, niveau), `section` (Exercice / Partie / I.), `consigne`, `texte_support`, `question`, `choix_qcm`, `ligne_reponse`, `bareme`, `tableau`, `note_bas` (bonus, rappel), `autre`.

### 8.4 Rule-based classifier
- Features: text patterns (French, in `config/rules.fr.yaml`: `^Exercice\s+\d+`, `\(\s*\d+(,\d+)?\s*pts?\s*\)`, `/\s*20`, `Nom\s*:`, dotted/underscore lines, `^[a-d]\)` …), style name, outline level, numbering, bold/size relative to body, alignment, position (first blocks, inside tables), length, punctuation (imperative instruction verbs list).
- Output: role + confidence in [0, 1].
- Blocks under the threshold (default 0.7) go to **one** batched LLM call with the compact view and the taxonomy; the answer is validated against the schema.
- Measured on the corpus: per-role precision/recall report (ticket T-207). Target: ≥ 90 % accuracy after LLM pass on the synthetic corpus.

### 8.5 Teacher review
The document is shown with a colour per role and a legend. Clicking a block opens a role menu. Corrections are stored in the profile (and as extra few-shot examples for future classifications of that teacher).

### 8.6 Profile (`profile.json`, versioned schema)
```jsonc
{
  "schema_version": 1,
  "name": "Contrôle 7e",
  "source_file_hash": "...",
  "page": {"orientation": "portrait", "margins_cm": {...}, "columns": 1},
  "roles": {
    "consigne": {"exemplar_para_xml": "<w:p>…</w:p>", "style_id": "...", "examples": ["Conjuguez …", "Complétez …"]},
    "question": {"exemplar_para_xml": "…", "list": {"abstract_num_xml": "…", "format": "1."}},
    "ligne_reponse": {"exemplar_para_xml": "…", "kind": "dots", "length_chars": 80}
    // one entry per role found
  },
  "structure": ["champ_entete", "titre", "info_epreuve", {"repeat": ["section", "consigne", "question+", "ligne_reponse*", "bareme?"]}],
  "conventions": {
    "address": "vous",               // tu | vous
    "points_total": 20,
    "points_format": "(4 pts)",
    "section_label": "Exercice {n} :",
    "level_hint": "7e année"
  }
}
```
- Exemplars are stored as XML of real paragraphs from the teacher's document (text emptied), plus required style and numbering definitions (copied into the target document when missing).
- Header/footer are kept inside `container.docx`, including images (school logo) and bidirectional text (Tunisian bilingual headers).

### 8.7 Renderer
Input: role-tagged content from the agent, e.g.
```json
[{"role": "section", "markup": "Exercice 1 : Le passé composé"},
 {"role": "consigne", "markup": "Conjuguez les verbes entre parenthèses. **(4 pts)**"},
 {"role": "question", "markup": "Hier, nous (aller) au cinéma."},
 {"role": "ligne_reponse", "count": 2}]
```
For each item: clone the role's exemplar paragraph, fill text from markup, handle list numbering restarts per section, generate answer lines from the stored kind/length. Unknown role → fallback to the closest role's exemplar, then to built-in neutral formatting.

### 8.8 Built-in templates
Two neutral templates ship with the app ("Devoir / contrôle", "Fiche d'exercices"), built through the same pipeline from documents we create, so there is only one code path.

### 8.9 Limits (communicated in the UI)
Layouts built "by hand" (spaces/tabs for alignment, tables used for positioning, text boxes) are detected less reliably; the review step compensates. `.doc` files: the app explains how to "Enregistrer sous… .docx" in Word. PDFs are not accepted as templates.

---

## 9. LLM gateway

### 9.1 Providers (free tiers only)
Gemini (Google AI Studio), Groq, Mistral (La Plateforme free tier), OpenRouter `:free` models (last resort: 50 requests/day without credits). All called through their **OpenAI-compatible** chat endpoints with `httpx`. The current list of free models, limits and capabilities is maintained in `docs/PROVIDERS.md` (dated) and `config/models.default.yaml`. **No model name appears in code.**

### 9.2 Configuration (`models.yaml`)
```yaml
providers:
  gemini:   {base_url: ..., key_name: gemini}
  groq:     {base_url: ..., key_name: groq}
  mistral:  {base_url: ..., key_name: mistral}
  openrouter: {base_url: ..., key_name: openrouter}
models:
  - id: gemini-flash        # internal alias
    provider: gemini
    name: "<provider model id>"
    limits: {rpm: ..., rpd: ..., tpm: ...}
    capabilities: {json_schema: true, json_object: true, context_tokens: ...}
    quality_fr: high        # used for ordering writing tasks
tasks:                       # ordered fallback chains
  route:        [groq-small, gemini-flash, mistral-small]
  plan:         [gemini-flash, mistral-small, groq-large, openrouter-free-1]
  write_fr:     [mistral-small, gemini-flash, openrouter-free-1]
  classify:     [gemini-flash, groq-large, mistral-small]
stt:            [groq-whisper]
```
The user config (data dir) overrides the shipped default; a settings screen lets an advanced user reorder chains and add models without a new release.

### 9.3 Router behaviour
For each call: take the task chain → skip models without a key, in cooldown, or over their local quota → call with timeout (connect 5 s, total 60 s) → on 429/5xx/timeout/invalid output: classify the error, set cooldown (use `Retry-After` / rate-limit headers when present, else exponential: 30 s, 2 min, 10 min; daily-limit errors → until next UTC midnight), try the next model. Network errors without any response trigger "hors ligne" mode, not cooldowns.

Every call is logged (provider, model, task, tokens if returned, latency, outcome) and the model actually used is returned to the UI.

### 9.4 Quota tracker
SQLite counters per model per minute/day, updated before/after calls, reconciled with provider headers when available. Exposed through `/quota` for the settings dashboard ("Gemini : ~1 200 requêtes restantes aujourd'hui").

### 9.5 Structured output
- Use `response_format: json_schema` when the model supports it, else `json_object`, else JSON in text.
- Parse → repair (tolerant parser for trailing commas, fences) → Pydantic validation.
- On failure: **one** retry on the same model with the validation error appended, then fall back to the next model.

### 9.6 Call budget (design target)

| Use case | Calls |
|---|---|
| Simple formatting ("mets les titres en gras") | 0 (fast path rules) |
| Edit instruction, clear target | 1 (route + plan merged) |
| Edit instruction, ambiguous | 2 |
| Learn a template | 0–1 |
| Create a document | 1 (outline) + 1 to N (content; one call if it fits the context, else one per section) |
| Invalid output | +1 retry |

### 9.7 Fake LLM
A scripted `FakeLLM` provider (responses keyed by task and prompt hash or explicit queue) is used in all tests. **Tests never hit the network.** A separate, manual `just eval-live` runs the evaluation against real providers.

---

## 10. Agent (LangGraph)

### 10.1 State
`conversation_id`, `document_id`, `version_id`, `instruction`, `selection_ids` (blocks selected in the UI), `intent`, `target_ids`, `outline`, `operations`, `validation_errors`, `attempts`, `proposal_id`, `events`, `model_used`, `messages` (last N turns, summarized beyond N).

### 10.2 Graph

```
            ┌──────────────┐
instruction►│  fast_path   │── matched ──► build ops ─────────────────────┐
            └──────┬───────┘                                            │
                   │ no match                                           ▼
            ┌──────▼───────┐   question   ┌──────────┐            ┌──────────┐
            │ route_plan   │─────────────►│ answer   │──► chat    │ validate │
            │ (1 LLM call) │              └──────────┘            └────┬─────┘
            └──┬────────┬──┘                                     ok │  │ errors (≤1)
       edit    │        │ create                                    │  ▼
               │        ▼                                           │ repair ─► validate
               │  ┌───────────┐  interrupt: teacher edits/approves  │
               │  │  outline  │─────────────────────────────┐       │
               │  └───────────┘                             ▼       │
               │                                  ┌──────────────┐  │
               │                                  │ write_content│──┤
               │                                  │ (per section)│  │
               │                                  └──────────────┘  │
               └────────────────────────────────────────────────────┤
                                                                    ▼
                                                     ┌────────────────────────┐
                                                     │ propose (executor on   │
                                                     │ copy + diff) → interrupt│
                                                     └────────────────────────┘
```

- **fast_path:** French rules (`config/rules.fr.yaml`) for frequent, unambiguous formatting commands, applied to the selection or to blocks of a given role ("toutes les consignes en gras", "police Arial 12", "justifie le texte", "marges 2 cm"). No LLM call.
- **route_plan:** one call returning `{intent, target_ids, operations?}`. When targets are clear, operations come back in the same call.
- **Target resolution:** UI selection first; else role map ("le deuxième exercice" → second `section` block and its children); else the model's choice, validated.
- **write_content:** uses the template profile (conventions + real excerpts as few-shots) and returns role-tagged content for the renderer.
- **Human in the loop:** proposals and outlines use LangGraph interrupts; state persisted with the SQLite checkpointer so an app restart does not lose a pending proposal.
- **Prompts:** French, one file per node in `backend/prompts/`, versioned, with few-shot examples; loaded and rendered with strict variable checks; a prompt change requires running the eval.

### 10.3 Events (SSE)
`step` (`analyse`, `planification`, `validation`, `rédaction`, `aperçu`), `model` (which model answered), `outline`, `proposal`, `answer`, `error` (French message + code), `done`.

---

## 11. Voice
- Frontend records with `MediaRecorder` (Opus/WebM), push-to-talk, max 60 s, level meter.
- Backend `POST /stt` → STT chain: Groq Whisper (free) first; local `faster-whisper` (`base`, int8, CPU) only if enabled in settings.
- Local STT is **off by default**. The settings screen offers it only if the machine passes a check (≥ 8 GB RAM, AVX2) and downloads the model on demand (~150 MB).
- The transcript appears in the input box for correction before sending. Language forced to French.

---

## 12. API (FastAPI)

All routes require `X-Session-Token`. Errors use RFC 9457 problem details with a stable `code` and a French `detail`.

| Route | Purpose |
|---|---|
| `GET /health`, `POST /shutdown` | lifecycle |
| `POST /documents/import` | import a .docx from a local path (from native dialog) → workspace |
| `POST /documents/new` | new document from a template |
| `GET /documents`, `GET /documents/{id}` | list recent, DocModel (+ roles) |
| `GET /documents/{id}/file?version=` | bytes for docx-preview |
| `GET /documents/{id}/versions`, `POST .../undo`, `POST .../redo` | history |
| `POST /documents/{id}/export` | copy head version to a chosen path |
| `POST /conversations/{id}/instructions` | start an instruction → SSE stream |
| `POST /proposals/{id}/accept` (optional op subset), `POST /proposals/{id}/reject` | decisions |
| `POST /outlines/{id}/approve` (with edits) | create flow |
| `POST /templates/learn`, `GET /templates/{id}/review`, `PUT /templates/{id}/roles`, `POST /templates/{id}/save`, `GET /templates`, `DELETE /templates/{id}` | template learning and library |
| `GET/PUT /settings`, `PUT /keys/{provider}`, `POST /keys/{provider}/test`, `DELETE /keys/{provider}` | settings and keys |
| `GET /quota` | quota dashboard |
| `POST /stt` | speech to text |
| `POST /diagnostics/export` | redacted zip of logs + config |

Limits: imported files ≤ 25 MB, ≤ 2 000 zip entries, uncompressed ≤ 200 MB (zip-bomb guard); XML parsed without external entity resolution.

---

## 13. Frontend

### 13.1 Screens (all text in French)
1. **Premier lancement:** welcome → API keys step (links to each console, paste, "Tester", at least one provider required) → optional: learn a first template → done.
2. **Accueil:** recent documents, "Ouvrir un document Word", "Nouveau document" (template picker), "Mes modèles".
3. **Éditeur:**
   - centre: page view (`docx-preview`), click to select blocks, highlight of targets/changes, role colours toggle;
   - right: chat (history, input, mic button, shortcut chips: QCM, dictée, version simplifiée, corrigé, grille d'évaluation, mettre en forme), progress steps, model badge;
   - proposal panel: list of operations with reasons, before/after diff, accept all / reject / accept selected;
   - top bar: undo/redo, versions timeline, export, document name, quota indicator.
4. **Créer:** description form (niveau, durée, thème, nombre d'exercices, barème) or free text → outline editor (reorder, rename, delete sections) → generate.
5. **Mes modèles:** library; "Apprendre un modèle" wizard: choose file → analysis → role review (colours + legend + click to fix) → name → save.
6. **Paramètres:** keys, model chains (advanced), quota dashboard, voice, versions retention, diagnostics export, about/updates.

### 13.2 Block mapping in the page view
`docx-preview` renders HTML without our IDs. Mapping strategy (validated by spike T-600): walk rendered paragraphs in document order and align them with DocModel blocks by order + normalized text; mismatches are tolerated and logged. Fallback if the spike fails: an "editing view" rendered from the DocModel by our own React components (approximate formatting, exact IDs), with the page view kept for visual checking.

### 13.3 Engineering rules
Feature folders; generated API types only; TanStack Query for all server data; SSE client with reconnect; all strings in `i18n/fr.json`; error boundary per screen; no `any`; components accessible (labels, focus, keyboard shortcuts: Ctrl+Z/Y, Ctrl+Entrée to send, Ctrl+S to export).

---

## 14. Security
- Keys in Windows Credential Manager via `keyring`; never logged; redaction filter in the logger and the diagnostics export.
- Backend bound to 127.0.0.1, random port, session token, CORS limited to the Tauri origin.
- Tauri CSP: `connect-src` limited to `http://127.0.0.1:*` (and the update endpoint in the Rust side); minimal capabilities; no shell access from the frontend.
- **Prompt injection:** document text is delimited and labelled as data; the model can only produce operations from the closed catalogue, validated before execution; worst case is a bad proposal the teacher rejects.
- No code or command is ever built from model output.
- Dependency hygiene: lockfiles, Dependabot, `pip-audit` and `pnpm audit` in CI.

## 15. Observability
Structured JSON logs (rotating, 5 × 5 MB), correlation ID per instruction across agent nodes and LLM calls; metrics in logs (latency, calls per instruction, fallback count). "Exporter le diagnostic" builds a redacted zip. No telemetry.

## 16. Packaging and release
- Backend: PyInstaller **onedir**, no UPX (fewer antivirus false positives), shipped as a Tauri resource and spawned by the Rust shell.
- Installer: Tauri NSIS bundle, per-user install (no admin), WebView2 bootstrapper, French installer language.
- **No code signing (0 $):** Windows SmartScreen shows "Windows a protégé votre ordinateur". The French user guide explains "Informations complémentaires → Exécuter quand même". If antivirus false positives appear, submit the build to Microsoft's false-positive portal.
- Auto-update: Tauri updater with a free signing key pair, manifests on GitHub Releases.
- CI: lint + tests on ubuntu and windows for every push; release workflow on tag builds the installer on `windows-latest` and drafts a release. Stay within free Actions minutes (Windows minutes count double on private repos).
- Size budget: installer < 150 MB.

## 17. Quality strategy
| Level | What | Tools |
|---|---|---|
| Unit | markup, validator, rules, router logic, quota, profile builder | pytest, hypothesis |
| Golden | executor and renderer outputs on the corpus (normalized XML snapshots) | pytest + snapshot files |
| Integration | API routes with FakeLLM, SSE flows, versions | pytest + httpx |
| Agent eval | `corpus/instructions.yaml`: correctness of ops, call count, latency (FakeLLM replay in CI; live run manual) | `just eval`, `just eval-live` |
| Frontend | components and hooks | vitest + Testing Library |
| E2E | main flows against the web build + real backend + FakeLLM | Playwright |
| Packaged | installer smoke test on Windows CI (install, launch, /health, open a doc, exit) | PowerShell script |
| Manual QA | checklist on a low-end Windows VM (4 GB RAM, 125 % scaling) | `docs/QA_CHECKLIST.md` |

Coverage gates: backend core packages (docmodel, operations, executor, templates, llm, agent) ≥ 85 % lines; whole backend ≥ 75 %.

**Test corpus:** no real teacher documents are available yet, so a generator builds a diverse synthetic corpus (see T-005), designed to mimic real-world mess. Real documents are added when available.

## 18. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Free models removed / limits cut | AI unavailable | Multi-provider chains, config outside code, `PROVIDERS.md` review each release, quota dashboard, clear degradation |
| Poor layouts break role detection | Wrong templates | Rules + LLM + mandatory teacher review; corrections reused |
| Formatting broken on rewrite | Trust loss | Markup + run cloning, golden tests, preview before apply, original never modified |
| Low-end hardware | Slow app | No local LLM, local STT off, onedir build, performance budgets measured in QA |
| SmartScreen / antivirus | Install friction | Guide with screenshots, onedir without UPX, false-positive submission |
| docx-preview mapping inaccurate | Selection UX | Spike first, fallback editing view |
| French quality varies by model | Weak content | `write_fr` chain ordered by French quality, eval on French instructions |
| Model output invalid | Failed instructions | Schema output, repair, one retry, fallback model |

## 19. Glossary
**Block:** a paragraph with a stable ID. **Operation:** one validated change from the catalogue. **Proposal:** operations + preview + diff awaiting approval. **Template:** container + profile learned from a teacher document. **Role:** semantic function of a block (consigne, question…). **Exemplar:** a real paragraph from a template, cloned to format new content. **Chain:** ordered list of models for a task.
