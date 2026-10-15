"""End-to-end: ``python -m assistant_prof --port 0`` as the desktop shell will run it."""

import json
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import IO

import httpx
import pytest

import assistant_prof

STARTUP_TIMEOUT_S = 30
EXIT_TIMEOUT_S = 15
STDIN_EOF_EXIT_TIMEOUT_S = 5
FORCED_DEADLINE_S = 1.0


def _read_first_line(stream: IO[str]) -> str:
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=lambda: lines.put(stream.readline()), daemon=True).start()
    try:
        return lines.get(timeout=STARTUP_TIMEOUT_S)
    except queue.Empty:
        pytest.fail("backend did not print its ready line in time")


MODULE = ("-m", "assistant_prof")
# The backend with a graceful shutdown that never completes and a 1 s deadline.
HANGING_SHUTDOWN = (
    "-c",
    "import asyncio, uvicorn\n"
    "from assistant_prof import main as m\n"
    "async def never(self, sockets=None):\n"
    "    await asyncio.Event().wait()\n"
    "uvicorn.Server.shutdown = never\n"
    f"m.SHUTDOWN_DEADLINE_S = {FORCED_DEADLINE_S}\n"
    "raise SystemExit(m.main())\n",
)


def _spawn(
    token: str, data_dir: Path, *, watch_stdin: bool, program: Sequence[str] = MODULE
) -> subprocess.Popen[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("ASSISTANT_PROF_")}
    env["ASSISTANT_PROF_TOKEN"] = token
    args = [sys.executable, *program, "--port", "0", "--data-dir", str(data_dir)]
    if watch_stdin:
        args.append("--exit-on-stdin-eof")
    return subprocess.Popen(  # noqa: S603  # fixed command, test-controlled arguments
        args,
        env=env,
        # Without the flag, stdin is at EOF from the start and must not stop the backend.
        stdin=subprocess.PIPE if watch_stdin else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )


def _stop(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.kill()
    process.wait(timeout=EXIT_TIMEOUT_S)


@pytest.fixture
def backend(token: str, tmp_path: Path) -> Iterator[subprocess.Popen[str]]:
    process = _spawn(token, tmp_path, watch_stdin=False)
    try:
        yield process
    finally:
        _stop(process)


@pytest.fixture
def watched_backend(token: str, tmp_path: Path) -> Iterator[subprocess.Popen[str]]:
    process = _spawn(token, tmp_path, watch_stdin=True)
    try:
        yield process
    finally:
        _stop(process)


def test_ready_handshake_health_and_shutdown(
    backend: subprocess.Popen[str], token: str, tmp_path: Path
) -> None:
    assert backend.stdout is not None
    assert backend.stderr is not None
    ready = json.loads(_read_first_line(backend.stdout))
    assert ready == {"event": "ready", "port": ready["port"], "version": assistant_prof.__version__}
    assert isinstance(ready["port"], int)
    assert ready["port"] > 0

    base = f"http://127.0.0.1:{ready['port']}"
    assert httpx.get(f"{base}/health").status_code == 401
    health = httpx.get(f"{base}/health", headers={"X-Session-Token": token})
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "version": assistant_prof.__version__}
    shutdown = httpx.post(f"{base}/shutdown", headers={"X-Session-Token": token})
    assert shutdown.status_code == 202

    assert backend.wait(timeout=EXIT_TIMEOUT_S) == 0
    assert backend.stdout.read() == ""  # nothing after the ready line
    assert backend.stderr.read() == ""  # not dev mode: logs go to the file only

    log_text = (tmp_path / "logs" / "assistant-prof.log").read_text(encoding="utf-8")
    events = [json.loads(line)["event"] for line in log_text.splitlines()]
    assert "server.ready" in events
    assert "shutdown.requested" in events
    assert token not in log_text


def test_closing_stdin_shuts_down_gracefully(
    watched_backend: subprocess.Popen[str], token: str, tmp_path: Path
) -> None:
    """Parent-death signal: the shell dying closes the pipe, and the backend exits by itself."""
    assert watched_backend.stdin is not None
    assert watched_backend.stdout is not None
    port = json.loads(_read_first_line(watched_backend.stdout))["port"]
    health = httpx.get(f"http://127.0.0.1:{port}/health", headers={"X-Session-Token": token})
    assert health.status_code == 200

    watched_backend.stdin.close()
    assert watched_backend.wait(timeout=STDIN_EOF_EXIT_TIMEOUT_S) == 0

    log_text = (tmp_path / "logs" / "assistant-prof.log").read_text(encoding="utf-8")
    events = [json.loads(line)["event"] for line in log_text.splitlines()]
    assert "shutdown.stdin_eof" in events
    assert events[-1] == "server.stopped"


@pytest.mark.parametrize("trigger", ["stdin_eof", "post_shutdown"])
def test_stuck_shutdown_is_forced_after_the_deadline(
    trigger: str, token: str, tmp_path: Path
) -> None:
    """A graceful shutdown that never completes still ends the process, with code 0."""
    process = _spawn(token, tmp_path, watch_stdin=True, program=HANGING_SHUTDOWN)
    try:
        assert process.stdin is not None
        assert process.stdout is not None
        port = json.loads(_read_first_line(process.stdout))["port"]
        requested = time.monotonic()
        if trigger == "stdin_eof":
            process.stdin.close()
        else:
            headers = {"X-Session-Token": token}
            response = httpx.post(f"http://127.0.0.1:{port}/shutdown", headers=headers)
            assert response.status_code == 202
        assert process.wait(timeout=FORCED_DEADLINE_S + STDIN_EOF_EXIT_TIMEOUT_S) == 0
        elapsed = time.monotonic() - requested
    finally:
        _stop(process)

    assert elapsed >= FORCED_DEADLINE_S * 0.9  # it waited for the deadline, then forced
    log_text = (tmp_path / "logs" / "assistant-prof.log").read_text(encoding="utf-8")
    records = [json.loads(line) for line in log_text.splitlines()]
    forced = [r for r in records if r["event"] == "shutdown.forced"]
    assert len(forced) == 1
    assert forced[0]["level"] == "warning"
    assert "server.stopped" not in [r["event"] for r in records]
