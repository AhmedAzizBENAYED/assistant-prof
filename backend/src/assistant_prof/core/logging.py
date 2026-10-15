"""Structured JSON logging with rotation, correlation IDs and secret redaction (ARCH §15).

Logs never go to stdout: stdout carries only the startup handshake line (ARCH §4).
"""

import logging
import logging.handlers
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

LOG_FILE_MAX_BYTES = 5 * 1024 * 1024
LOG_FILE_BACKUPS = 4  # 5 files in total, 5 MB each
REDACTED = "[REDACTED]"

# Keys whose values are always hidden (compared after lower-casing and "-" -> "_").
_SENSITIVE_KEYS = frozenset(
    {"token", "session_token", "x_session_token", "api_key", "apikey", "key", "authorization"}
    | {"password", "secret"}
)
# Suffixes rather than substrings, so counters such as "prompt_tokens" stay visible.
_SENSITIVE_SUFFIXES = ("_key", "_token", "_secret", "_password")

# Secrets recognised inside any string value: provider key formats and bearer tokens.
# The lookbehind keeps words such as "task-scheduler" intact.
_SECRET_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])(?:"
    r"sk-[A-Za-z0-9_-]{8,}"  # OpenAI-style keys (OpenRouter and others)
    r"|gsk_[A-Za-z0-9]{8,}"  # Groq
    r"|AIza[0-9A-Za-z_-]{20,}"  # Google AI Studio
    r"|(?i:bearer)\s+[A-Za-z0-9._~+/-]+=*"
    r")"
)

_OWN_HANDLER_ATTR = "_assistant_prof_handler"


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith(_SENSITIVE_SUFFIXES)


class Redactor:
    """structlog processor that hides secrets anywhere in the event, tracebacks included."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        self._secrets = tuple(s for s in secrets if s)

    def redact_text(self, text: str) -> str:
        """Replace known secret values and secret-looking strings."""
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return _SECRET_PATTERN.sub(REDACTED, text)

    def _redact(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, dict):
            return {
                k: REDACTED if isinstance(k, str) and _is_sensitive_key(k) else self._redact(v)
                for k, v in value.items()
            }
        if isinstance(value, list | tuple):
            return [self._redact(v) for v in value]
        return value

    def __call__(self, logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
        """Redact the event dict."""
        redacted: EventDict = self._redact(event_dict)
        return redacted


def _shared_processors() -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]


def build_formatter(redactor: Redactor) -> structlog.stdlib.ProcessorFormatter:
    """JSON formatter used by every handler, for structlog and stdlib records alike."""
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_shared_processors(),
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            redactor,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
    )


def configure_logging(
    log_file: Path,
    *,
    level: str = "INFO",
    to_stderr: bool = False,
    secrets: Iterable[str] = (),
) -> None:
    """Route structlog and stdlib logging (uvicorn included) to JSON handlers.

    ``log_file`` rotates at 5 MB, keeping 5 files. ``to_stderr`` adds a stderr copy (dev mode).
    ``secrets`` are literal values to scrub, such as the session token.
    Calling it again replaces the handlers installed by the previous call.
    """
    reset_logging()
    formatter = build_formatter(Redactor(secrets))

    log_file.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(
            log_file, maxBytes=LOG_FILE_MAX_BYTES, backupCount=LOG_FILE_BACKUPS, encoding="utf-8"
        )
    ]
    if to_stderr:
        handlers.append(logging.StreamHandler(sys.stderr))

    root = logging.getLogger()
    for handler in handlers:
        handler.setFormatter(formatter)
        setattr(handler, _OWN_HANDLER_ATTR, True)
        root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn installs nothing when started with log_config=None; make sure it propagates.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    structlog.configure(
        processors=[
            *_shared_processors(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )


def reset_logging() -> None:
    """Close and remove the handlers installed by :func:`configure_logging`."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _OWN_HANDLER_ATTR, False):
            root.removeHandler(handler)
            handler.close()
