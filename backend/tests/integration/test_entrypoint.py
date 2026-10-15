"""End-to-end: ``python -m assistant_prof --port 0`` as the desktop shell will run it."""

import json
import os
import queue
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import IO

import httpx
import pytest

import assistant_prof

STARTUP_TIMEOUT_S = 30
EXIT_TIMEOUT_S = 15
STDIN_EOF_EXIT_TIMEOUT_S = 5


def _read_first_line(stream: IO[str]) -> str:
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=lambda: lines.put(stream.readline()), daemon=True).start()
    try:
        return lines.get(timeout=STARTUP_TIMEOUT_S)
    except queue.Empty:
        pytest.fail("backend did not print its ready line in time")


def _spawn(token: str, data_dir: Path, *, watch_stdin: bool) -> subprocess.Popen[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("ASSISTANT_PROF_")}
    env["ASSISTANT_PROF_TOKEN"] = token
    args = [sys.executable, "-m", "assistant_prof", "--port", "0", "--data-dir", str(data_dir)]
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
