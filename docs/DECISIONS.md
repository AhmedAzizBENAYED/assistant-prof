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
Accepted · 2026-10-15
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
Accepted · 2026-10-15
- **Decision:** block IDs come from Word's paragraph IDs; missing ones are generated and written into the working copy.
- **Why:** IDs survive save/reload, undo/redo and versions, so operations and UI selections stay valid.

### ADR-014, Voice: Groq Whisper first, local STT optional and off by default
Accepted · 2026-10-15
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
Accepted · 2026-10-15
- **Decision:** one SQLite database (SQLAlchemy 2 + Alembic) for history, conversations, templates index, quota counters, settings; LangGraph checkpoints in SQLite too.

### ADR-020, Synthetic corpus until real documents exist
Accepted · 2026-10-15
- **Decision:** no real teacher documents are available; a generator builds a diverse synthetic corpus (styled, hand-formatted, table layouts, logos, bilingual headers, text boxes, tracked changes…). Real documents are added when available and become the reference.
- **Cost:** risk of surprises on real documents; mitigated by deliberately messy fixtures and the review step.
