# PyInstaller spec for the backend sidecar (ADR-035, ARCH §16). Walking-skeleton version:
# T-802 adds data files (prompts, config, templates, migrations) and the remaining hidden imports.
# Build with `just build-backend`; output in backend/dist/assistant-prof-backend/.
# ruff: noqa  (executed by PyInstaller, which injects Analysis, PYZ, EXE and COLLECT)

NAME = "assistant-prof-backend"

# Uvicorn imports these by string from its config; we pin h11, asyncio and lifespan "auto" (ADR-038).
HIDDEN_IMPORTS = [
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.loops.asyncio",
    "uvicorn.lifespan.on",
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
