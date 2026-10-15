# Single entry point for all commands. Keep in sync with the table in CLAUDE.md.
# Recipes avoid `cd` and shell-specific syntax so they run in sh (Linux) and PowerShell (Windows).

set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command"]

tauri_manifest := "desktop/src-tauri/Cargo.toml"

# List available recipes
default:
    @just --list --unsorted

# Install all toolchains' dependencies
setup:
    uv sync --directory backend --locked
    pnpm install --frozen-lockfile
    cargo fetch --manifest-path {{ tauri_manifest }} --locked
    uvx pre-commit@4.7.0 install

# Backend + frontend + Tauri in dev mode (the backend joins in T-003/T-801)
dev:
    pnpm --dir desktop tauri dev

# All linters, type checks and tests (must pass before commit)
check: check-backend check-frontend check-desktop

# Backend: ruff, mypy --strict, pytest with coverage
check-backend: lint-backend test-backend

# Frontend: eslint, prettier, tsc, vitest
check-frontend: lint-frontend test-frontend

# Desktop shell: rustfmt and clippy
check-desktop:
    cargo fmt --manifest-path {{ tauri_manifest }} --check
    cargo clippy --manifest-path {{ tauri_manifest }} --all-targets --locked -- -D warnings

# Backend linters and type checks
lint-backend:
    uv run --directory backend --locked ruff check .
    uv run --directory backend --locked ruff format --check .
    uv run --directory backend --locked mypy

# Frontend linters, formatting and type checks
lint-frontend:
    pnpm --dir frontend lint
    pnpm --dir frontend format:check
    pnpm --dir frontend typecheck

# Backend test suite
test-backend:
    uv run --directory backend --locked pytest

# Frontend test suite
test-frontend:
    pnpm --dir frontend test

# Format all code in place
fmt:
    uv run --directory backend --locked ruff check --fix .
    uv run --directory backend --locked ruff format .
    pnpm --dir frontend format
    cargo fmt --manifest-path {{ tauri_manifest }}

# Playwright end-to-end tests
e2e:
    @echo "not implemented: T-602"
    @exit 1

# Regenerate the TypeScript API client from OpenAPI
gen-api:
    @echo "not implemented: T-504"
    @exit 1

# Regenerate the synthetic test corpus
corpus:
    @echo "not implemented: T-005a"
    @exit 1

# Agent evaluation with FakeLLM replay
eval:
    @echo "not implemented: T-407"
    @exit 1

# Evaluation against real free providers (manual, uses quota)
eval-live:
    @echo "not implemented: T-407"
    @exit 1

# Template-learning accuracy report on the corpus
eval-templates:
    @echo "not implemented: T-207"
    @exit 1

# PyInstaller backend + Tauri installer
build:
    @echo "not implemented: T-802, T-803"
    @exit 1
