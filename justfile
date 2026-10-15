# Single entry point for all commands. Keep in sync with the table in CLAUDE.md.
# Recipes avoid `cd` and shell-specific syntax so they run in sh (Linux) and PowerShell (Windows).

set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command"]

tauri_manifest := "desktop/src-tauri/Cargo.toml"
exe := if os_family() == "windows" { ".exe" } else { "" }
# Paths relative to backend/, where `uv run --directory backend` runs the scripts.
backend_exe := "dist/assistant-prof-backend/assistant-prof-backend" + exe
app_exe := "../desktop/src-tauri/target/release/assistant-prof" + exe

# List available recipes
default:
    @just --list --unsorted

# Install all toolchains' dependencies
setup:
    uv sync --directory backend --locked
    pnpm install --frozen-lockfile
    cargo fetch --manifest-path {{ tauri_manifest }} --locked
    uvx pre-commit@4.7.0 install

# Backend + frontend + Tauri in dev mode (needs `just build-backend` once; T-801 hardens it)
dev:
    pnpm --dir desktop tauri dev

# Backend alone in dev mode: fresh random token printed once, OS-assigned port in the ready line
backend *args:
    uv run --directory backend --locked python scripts/dev_backend.py {{ args }}

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
    cargo test --manifest-path {{ tauri_manifest }} --locked

# Backend linters and type checks
lint-backend:
    uv run --directory backend --locked ruff check . ../corpus/generator
    uv run --directory backend --locked ruff format --check . ../corpus/generator
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

# Dependency audits (not part of `check`: results change over time; non-blocking in CI)
audit: audit-backend audit-frontend audit-desktop

# pip-audit on the locked backend dependencies
audit-backend:
    uv export --directory backend --locked --quiet --no-emit-project --output-file build/audit-requirements.txt
    uvx pip-audit@2.10.1 --disable-pip --requirement backend/build/audit-requirements.txt

# pnpm audit on the workspace lockfile
audit-frontend:
    pnpm audit

# cargo audit on the desktop lockfile (needs `cargo install cargo-audit` locally)
audit-desktop:
    cargo audit --file desktop/src-tauri/Cargo.lock

# Format all code in place
fmt:
    uv run --directory backend --locked ruff check --fix . ../corpus/generator
    uv run --directory backend --locked ruff format . ../corpus/generator
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

# Regenerate the synthetic test corpus into corpus/docs/ (byte-identical across runs)
corpus:
    uv run --directory backend --locked python ../corpus/generator/build_corpus.py

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

# Package the backend with PyInstaller (onedir, no UPX) into backend/dist/assistant-prof-backend
build-backend:
    uv run --directory backend --locked --group packaging pyinstaller packaging/assistant-prof-backend.spec --noconfirm --clean --distpath dist --workpath build/pyinstaller

# Bundle size, cold start and idle memory of the packaged app; report in docs/reports/
measure *args: build-backend
    pnpm --dir desktop tauri build --no-bundle
    uv run --directory backend --locked python scripts/measure.py --backend-exe {{ backend_exe }} --app-exe {{ app_exe }} --out-dir ../docs/reports {{ args }}

# PyInstaller backend + Tauri installer
build:
    @echo "not implemented: T-802, T-803"
    @exit 1
