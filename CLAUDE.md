# CLAUDE.md: working rules for this repository

## What we are building
**Assistant Prof**: a Windows desktop app (Tauri 2 + React/Vite + Python FastAPI sidecar) that helps French teachers edit and create Word documents with free AI models. Teachers give instructions by text or voice; the system proposes changes as validated operations; the teacher approves; a new version is saved. It learns each teacher's templates from their own documents.

Read before any work:
- `docs/ARCHITECTURE.md`: the agreed design. Follow it.
- `docs/DECISIONS.md`: why things are the way they are.
- `docs/TICKETS.md`: the backlog. We work **one ticket at a time**.

## Workflow for every ticket (mandatory)
1. **Read** the ticket, its dependencies and the architecture sections it cites. Inspect the existing code.
2. **Plan, then stop.** Present a short plan: files to create/change, design choices, tests you will write, open questions. **Do not write or change any code until the user explicitly approves the plan.**
3. **Implement** in small steps, tests alongside the code.
4. **Verify:** run `just check` (lint, types, tests). All must pass. Show the result. If a test fails intermittently, save the full failing output to `docs/reports/flaky/<date>-<test-or-recipe>.log` **before** rerunning, so it can be diagnosed.
5. **Docs:** update `ARCHITECTURE.md` if behaviour or structure changed; add an ADR in `DECISIONS.md` for any new decision or deviation; tick the ticket in `TICKETS.md`.
6. **Commit, never push** with a Conventional Commit message referencing the ticket (`feat(executor): rewrite op preserves runs [T-105]`). One ticket = one or a few focused commits, directly on `main` (no branches, no PRs; the only PRs are Dependabot's, merged by the user once CI is green). Then stop and tell the user the commit is ready to push. The user pushes and checks CI (`ci-ok`); if they report a red run, fixing it comes before anything else. Never push or tag.
7. **Report:** what was done, test results, anything left or risky.

If the ticket is unclear, contradicts the architecture, or is bigger than expected: say so in the plan and propose a split instead of improvising.

## Non-negotiable rules
- Models **never** write files or XML. Only operations from the catalogue, validated, then applied by the executor (ADR-005).
- **Never modify the original document**; all writes are atomic (ADR-006).
- **No model names or provider URLs in code.** They live in `backend/config/models.default.yaml` (ADR-009).
- **No network in tests.** Use `FakeLLM` and recorded fixtures. Live calls only in `just eval-live`.
- **No secrets** in code, config files, logs, fixtures or commits. Keys go through `keyring`.
- Everything the teacher sees is **French** (`frontend/src/i18n/fr.json`, prompts, API error `detail`). Code, comments, docs, commit messages are **English**.
- Locked content (text boxes, equations, drawings, fields, content controls, tracked changes) is never modified.
- Do not add a dependency without saying why in the plan; prefer the standard library and what is already in the stack. Never add a paid service.
- Keep performance budgets in mind (4 GB RAM laptops): no heavy imports at startup, lazy-load optional features.

## Code standards
**Python (backend/)**
- Python 3.12, `uv`. Type hints everywhere; `mypy --strict` clean; `ruff` (lint + format).
- Pydantic v2 models for all external data (API, LLM output, config, profile.json).
- Pure functions for logic (validator, rules, diff, router decisions); I/O at the edges.
- Typed error hierarchy in `core/errors.py`; API returns RFC 9457 problem details with stable `code` + French `detail`.
- Logging via `structlog`, with correlation ID; never log document text at INFO or above, never log keys.
- Tests: pytest (+ hypothesis for parsers/validators), golden snapshot tests for executor/renderer. Coverage gates: core packages ≥ 85 %.

**TypeScript (frontend/)**
- `strict: true`, no `any`, no non-null assertions without a comment.
- API types generated from OpenAPI (`just gen-api`), never hand-written.
- TanStack Query for server state, Zustand for UI state, feature folders.
- Accessible components (labels, focus order, keyboard shortcuts). Vitest + Testing Library; Playwright for E2E.

**Rust (desktop/src-tauri/)**
- Keep the shell thin: sidecar lifecycle, dialogs, updater, single instance. `cargo clippy -D warnings`.

## Commands (via `justfile`)
| Command | What it does |
|---|---|
| `just setup` | install all toolchains' dependencies |
| `just dev` | backend + frontend + Tauri in dev mode |
| `just backend` | backend alone in dev mode: fresh random session token printed once, OS-assigned port shown in the ready line |
| `just check` | all linters, type checks and tests (must pass before commit) |
| `just test-backend` / `just test-frontend` / `just e2e` | test suites |
| `just gen-api` | regenerate the TypeScript API client from OpenAPI |
| `just corpus` | regenerate the synthetic test corpus |
| `just eval` | agent evaluation with FakeLLM replay |
| `just eval-live` | evaluation against real free providers (manual, uses quota) |
| `just eval-templates` | template-learning accuracy report on the corpus |
| `just build` | PyInstaller backend + Tauri installer |
| `just build-backend` | PyInstaller onedir backend only, into `backend/dist/assistant-prof-backend/` (started by `just dev` and the release shell) |
| `just measure` | release build, then bundle size, cold start and idle memory (RSS and USS) against the ARCHITECTURE §2 budgets, for a new database and a database at head; report in `docs/reports/` |
| `just fmt` | format all code in place (ruff, prettier, rustfmt) |
| `just check-backend` / `just check-frontend` / `just check-desktop` | the parts of `just check`, one stack each |
| `just audit` | dependency audits: pip-audit, pnpm audit, cargo audit (not part of `check`; non-blocking in CI) |

(Commands are created in T-001; keep this table in sync with the `justfile`. Recipes of later tickets are stubs that print `not implemented: T-xxx` and exit 1; `just check` never calls a stub.)

## Definition of Done
- Acceptance criteria of the ticket all met and demonstrated.
- `just check` green locally; CI green.
- Tests cover the new behaviour, including failure paths.
- No TODO without a ticket reference.
- Docs and ADRs updated.
- User approved the plan before implementation and the result after it.
