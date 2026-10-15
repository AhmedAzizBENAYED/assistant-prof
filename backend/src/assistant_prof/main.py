"""Backend entry point: ``python -m assistant_prof --port N`` (ADR-038).

Startup handshake (ARCH §4): once the server is listening, exactly one JSON line is written to
stdout, ``{"event":"ready","port":<port>,"version":"<version>"}``. Nothing else is ever written to
stdout: logs go to the log file (and stderr in dev mode), and stray prints are sent to stderr.

Parent-death detection (ADR-038): with ``--exit-on-stdin-eof`` the backend shuts down gracefully,
as on ``POST /shutdown``, when its stdin reaches end of file. The desktop shell keeps the write end
of that pipe open, so the OS closes it whenever the shell dies, even when it is killed.

Shutdown deadline (ADR-039): once a shutdown is requested (stdin EOF or ``POST /shutdown``), the
process is force-exited with code 0 if the graceful shutdown has not completed within 5 s.
"""

import argparse
import json
import logging
import os
import sys
import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, TextIO

import structlog
import uvicorn

from assistant_prof import __version__
from assistant_prof.api.app import create_app
from assistant_prof.core.config import Settings, load_settings
from assistant_prof.core.errors import ConfigError
from assistant_prof.core.logging import configure_logging, reset_logging
from assistant_prof.core.paths import DataPaths

HOST = "127.0.0.1"
EXIT_CONFIG_ERROR = 2
SHUTDOWN_DEADLINE_S = 5.0  # hard limit for a graceful shutdown once requested (ADR-039)
_STDIN_CHUNK = 4096

log = structlog.get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """CLI arguments. The token is deliberately absent: it comes from the environment."""
    parser = argparse.ArgumentParser(
        prog="assistant_prof",
        description="Assistant Prof backend. Needs ASSISTANT_PROF_TOKEN in the environment.",
    )
    parser.add_argument(
        "--port", type=int, required=True, help="port on 127.0.0.1; 0 lets the OS pick one"
    )
    parser.add_argument("--data-dir", type=Path, help="data directory (default: per-user dir)")
    parser.add_argument("--dev", action="store_true", help="dev mode (refused in packaged builds)")
    parser.add_argument(
        "--exit-on-stdin-eof",
        action="store_true",
        help="shut down when stdin is closed (the desktop shell's parent-death signal)",
    )
    return parser


def is_frozen() -> bool:
    """Tell whether this is a PyInstaller build."""
    return bool(getattr(sys, "frozen", False))


def ready_line(port: int) -> str:
    """Return the handshake line read by the desktop shell."""
    return json.dumps(
        {"event": "ready", "port": port, "version": __version__}, separators=(",", ":")
    )


class _Server(uvicorn.Server):
    """Uvicorn server that reports the port it actually listens on once started."""

    def __init__(self, config: uvicorn.Config, on_ready: Callable[[int], None]) -> None:
        super().__init__(config)
        self._on_ready = on_ready

    async def startup(self, sockets: list[object] | None = None) -> None:  # type: ignore[override]
        await super().startup(sockets=sockets)  # type: ignore[arg-type]
        if self.started:
            port: int = self.servers[0].sockets[0].getsockname()[1]
            self._on_ready(port)


def watch_stdin(stream: BinaryIO, on_eof: Callable[[], None]) -> threading.Thread:
    """Start a daemon thread that discards ``stream`` and calls ``on_eof`` at end of file."""

    def run() -> None:
        try:
            while stream.read(_STDIN_CHUNK):
                pass
        except (OSError, ValueError):  # broken or closed pipe: the parent is gone as well
            pass
        log.info("shutdown.stdin_eof")
        on_eof()

    thread = threading.Thread(target=run, name="stdin-watch", daemon=True)
    thread.start()
    return thread


@contextmanager
def _stdout_reserved() -> Iterator[TextIO | None]:
    """Yield the real stdout and redirect ``sys.stdout`` to stderr until exit."""
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        yield real_stdout
    finally:
        sys.stdout = real_stdout


def force_exit() -> None:
    """Exit the process at once with code 0, after flushing the log handlers."""
    logging.shutdown()
    os._exit(0)


class ShutdownDeadline:
    """Force-exits the process if a requested graceful shutdown takes longer than ``seconds``."""

    def __init__(self, seconds: float, on_expiry: Callable[[], None]) -> None:
        self._seconds = seconds
        self._on_expiry = on_expiry
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._cancelled = False

    def start(self) -> None:
        """Start the countdown; later calls (a second shutdown request) do nothing."""
        with self._lock:
            if self._timer is not None or self._cancelled:
                return
            self._timer = threading.Timer(self._seconds, self._expire)
            self._timer.name = "shutdown-deadline"
            self._timer.daemon = True
            self._timer.start()

    def cancel(self) -> None:
        """Stop the countdown for good: the shutdown completed."""
        with self._lock:
            self._cancelled = True
            if self._timer is not None:
                self._timer.cancel()

    def _expire(self) -> None:
        log.warning("shutdown.forced", deadline_s=self._seconds)
        self._on_expiry()


def serve(settings: Settings, handshake: TextIO | None, stdin: BinaryIO | None = None) -> None:
    """Run uvicorn until shutdown; write the ready line to ``handshake``.

    If ``stdin`` is given, its end of file triggers the same graceful shutdown as ``/shutdown``.
    Once a shutdown is requested, the process is force-exited (code 0) if it has not completed
    within ``SHUTDOWN_DEADLINE_S`` (ADR-039).
    """

    def announce(port: int) -> None:
        log.info("server.ready", port=port, version=__version__, dev=settings.dev)
        if handshake is not None:
            handshake.write(ready_line(port) + "\n")
            handshake.flush()

    config = uvicorn.Config(
        app=None,  # type: ignore[arg-type]  # set below, once the server exists
        host=HOST,
        port=settings.port,
        log_config=None,
        access_log=False,  # requests are logged by RequestContextMiddleware
        server_header=False,
        http="h11",
        ws="none",
        loop="asyncio",
    )
    server = _Server(config, on_ready=announce)

    deadline = ShutdownDeadline(SHUTDOWN_DEADLINE_S, force_exit)

    def request_shutdown() -> None:
        server.should_exit = True
        deadline.start()

    config.app = create_app(settings, request_shutdown=request_shutdown)
    if stdin is not None:
        watch_stdin(stdin, request_shutdown)
    try:
        server.run()
    finally:
        deadline.cancel()  # graceful shutdown completed (or failed) in time


def _stdin_for(settings: Settings) -> BinaryIO | None:
    """Return the stream to watch for parent death, if enabled and available."""
    if not settings.exit_on_stdin_eof:
        return None
    if sys.stdin is None:  # no stdin at all (e.g. pythonw): there is no parent pipe to watch
        log.warning("stdin_watch.unavailable")
        return None
    return sys.stdin.buffer


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, configure logging and run the server. Returns the exit code."""
    args = build_parser().parse_args(argv)
    overrides: dict[str, object] = {"port": args.port}
    if args.data_dir is not None:
        overrides["data_dir"] = args.data_dir
    if args.dev:
        overrides["dev"] = True
    if args.exit_on_stdin_eof:
        overrides["exit_on_stdin_eof"] = True

    with _stdout_reserved() as handshake:
        try:
            settings = load_settings(overrides, frozen=is_frozen())
        except ConfigError as exc:
            sys.stderr.write(f"assistant_prof: {exc}\n")
            return EXIT_CONFIG_ERROR

        paths = DataPaths.resolve(settings.data_dir)
        paths.ensure()
        configure_logging(
            paths.log_file,
            level=settings.log_level,
            to_stderr=settings.dev,
            secrets=[settings.token.get_secret_value()],
        )
        try:
            log.info("server.starting", version=__version__, data_dir=str(paths.root))
            serve(settings, handshake, _stdin_for(settings))
            log.info("server.stopped")
        finally:
            reset_logging()
    return 0
