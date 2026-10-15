# Assistant Prof

Windows desktop app that helps French teachers edit and create Word documents with free AI models.
Tauri 2 shell, React + Vite frontend, Python FastAPI sidecar.

Design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · Decisions: [docs/DECISIONS.md](docs/DECISIONS.md) · Backlog: [docs/TICKETS.md](docs/TICKETS.md) · Working rules: [CLAUDE.md](CLAUDE.md)

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12 | `uv` installs it if missing (`uv python install 3.12`) |
| [uv](https://docs.astral.sh/uv/) | 0.13+ | Python environments and lockfile |
| Node.js | current LTS (24+) | |
| [pnpm](https://pnpm.io/) | 12 (pinned in `package.json`) | `corepack enable` picks the pinned version |
| Rust | stable (msvc on Windows) | via [rustup](https://rustup.rs/); `rustfmt` and `clippy` are installed automatically from `rust-toolchain.toml` |
| [just](https://just.systems/) | 1.40+ | command runner |
| git | | |

**Windows:** [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) with the
*Desktop development with C++* workload (MSVC compiler and linker) **and a Windows 10/11 SDK**.
WebView2 is preinstalled on Windows 10 (22H2+) and 11.

**Linux:** the Tauri system packages, for example on Debian/Ubuntu:

```sh
sudo apt install libwebkit2gtk-4.1-dev build-essential curl wget file libxdo-dev \
  libssl-dev libayatana-appindicator3-dev librsvg2-dev
```

See the [Tauri prerequisites](https://v2.tauri.app/start/prerequisites/) for other distributions.

## Quick start

```sh
git clone <repo-url> assistant-prof
cd assistant-prof
just setup   # install Python, Node and Rust dependencies, install pre-commit hooks
just check   # linters, type checks and tests (must pass before every commit)
just dev     # open the desktop app in dev mode with hot reload
```

The first `just check` and `just dev` compile Tauri and take a few minutes; later runs are incremental.
Run `just` alone to list every command.

## Layout

```
backend/    Python sidecar (uv project, src/assistant_prof)
frontend/   React + Vite + TypeScript (strict)
desktop/    Tauri 2 shell (src-tauri/) and the Tauri CLI
corpus/     synthetic test corpus and instruction set
docs/       architecture, decisions, backlog
```
