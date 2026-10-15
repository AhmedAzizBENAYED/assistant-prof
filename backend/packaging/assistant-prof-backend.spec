# PyInstaller spec for the backend sidecar (ADR-035, ARCH §16). Walking-skeleton version:
# T-802 adds the other data files (prompts, config, templates) and the remaining hidden imports.
# Build with `just build-backend`; output in backend/dist/assistant-prof-backend/.
# ruff: noqa  (executed by PyInstaller, which injects Analysis, PYZ, EXE and COLLECT)

from pathlib import Path

NAME = "assistant-prof-backend"

# Uvicorn imports these by string from its config; we pin h11, asyncio and lifespan "auto" (ADR-038).
HIDDEN_IMPORTS = [
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.loops.asyncio",
    "uvicorn.lifespan.on",
    # Imported only by migrations/env.py, which PyInstaller does not analyse (ADR-040).
    "assistant_prof.persistence.models",
]

# Alembic loads env.py and the revisions from files at startup (ADR-040), so they ship as data.
# Listed file by file so the source tree's __pycache__ folders stay out.
MIGRATIONS = Path(SPECPATH, "..", "src", "assistant_prof", "persistence", "migrations")
DATAS = [
    (str(source), str(Path("assistant_prof/persistence/migrations", source.parent.relative_to(MIGRATIONS))))
    for source in sorted(MIGRATIONS.rglob("*"))
    if source.suffix in {".py", ".mako"}
]

# Standard-library parts the backend never uses; leaving them out keeps the bundle small.
EXCLUDES = [
    "tkinter",
    "unittest",
    "pydoc",
    "doctest",
    "lib2to3",
    "idlelib",
    "test",
]

a = Analysis(
    ["entry.py"],
    pathex=["../src"],
    datas=DATAS,
    hiddenimports=HIDDEN_IMPORTS,
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir
    name=NAME,
    debug=False,
    strip=False,
    upx=False,  # no UPX: fewer antivirus false positives (ARCH §16)
    # Console subsystem: stdout must be a real pipe for the ready line. The desktop shell
    # hides the console window with CREATE_NO_WINDOW.
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=NAME,
)
