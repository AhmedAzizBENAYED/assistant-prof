"""Run the backend alone in dev mode (``just backend``).

A fresh random session token is generated on each launch and printed once; the backend listens
on an OS-assigned port, shown in its ready line. Data goes to ``backend/build/dev-data`` so dev
runs never touch the real user data directory. Extra arguments are passed to the backend.
"""

import os
import secrets
import subprocess
import sys
from collections.abc import Sequence

DEV_DATA_DIR = "build/dev-data"


def backend_command(extra_args: Sequence[str]) -> list[str]:
    """Return the backend command line; later arguments override earlier ones."""
    return [
        sys.executable,
        "-m",
        "assistant_prof",
        "--port",
        "0",
        "--dev",
        "--data-dir",
        DEV_DATA_DIR,
        *extra_args,
    ]


def main(argv: Sequence[str]) -> int:
    """Start the backend and wait for it; Ctrl+C stops it."""
    token = secrets.token_urlsafe(32)
    sys.stdout.write(f"Session token (X-Session-Token) for this run: {token}\n")
    sys.stdout.flush()
    env = {**os.environ, "ASSISTANT_PROF_TOKEN": token}
    try:
        return subprocess.call(backend_command(argv), env=env)  # noqa: S603  # fixed command
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
