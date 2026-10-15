"""Backend entry point: ``python -m assistant_prof --port N`` (ADR-038).

Startup handshake (ARCH §4): once the server is listening, exactly one JSON line is written to
stdout, ``{"event":"ready","port":<port>,"version":"<version>"}``. Nothing else is ever written to
stdout: logs go to the log file (and stderr in dev mode), and stray prints are sent to stderr.
"""

import argparse
import json
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

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


@contextmanager
def _stdout_reserved() -> Iterator[TextIO | None]:
    """Yield the real stdout and redirect ``sys.stdout`` to stderr until exit."""
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        yield real_stdout
    finally:
        sys.stdout = real_stdout


def serve(settings: Settings, handshake: TextIO | None) -> None:
    """Run uvicorn until shutdown; write the ready line to ``handshake``."""

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

    def request_shutdown() -> None:
        server.should_exit = True

    config.app = create_app(settings, request_shutdown=request_shutdown)
    server.run()


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, configure logging and run the server. Returns the exit code."""
    args = build_parser().parse_args(argv)
    overrides: dict[str, object] = {"port": args.port}
    if args.data_dir is not None:
        overrides["data_dir"] = args.data_dir
    if args.dev:
        overrides["dev"] = True

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
            serve(settings, handshake)
            log.info("server.stopped")
        finally:
            reset_logging()
    return 0
