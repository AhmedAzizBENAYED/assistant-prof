import json
import logging
import logging.handlers
from pathlib import Path
from typing import Any

import pytest
import structlog

from assistant_prof.core.logging import (
    LOG_FILE_BACKUPS,
    LOG_FILE_MAX_BYTES,
    REDACTED,
    Redactor,
    configure_logging,
    reset_logging,
)

FAKE_KEY = "sk-or-v1-0123456789abcdef0123456789abcdef"


def read_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def log_file(tmp_path: Path, token: str) -> Path:
    path = tmp_path / "logs" / "test.log"
    configure_logging(path, level="DEBUG", secrets=[token])
    return path


def test_structlog_and_stdlib_records_are_json(log_file: Path) -> None:
    structlog.get_logger("assistant_prof.test").info("hello", count=3, texte="élève")
    logging.getLogger("uvicorn.error").warning("from %s", "uvicorn")
    first, second = read_lines(log_file)
    assert first["event"] == "hello"
    assert first["count"] == 3
    assert first["texte"] == "élève"
    assert first["level"] == "info"
    assert first["logger"] == "assistant_prof.test"
    assert first["timestamp"].endswith("Z")
    assert second["event"] == "from uvicorn"
    assert second["level"] == "warning"


def test_correlation_id_is_attached(log_file: Path) -> None:
    with structlog.contextvars.bound_contextvars(correlation_id="corr-1234"):
        structlog.get_logger().info("inside")
    structlog.get_logger().info("outside")
    inside, outside = read_lines(log_file)
    assert inside["correlation_id"] == "corr-1234"
    assert "correlation_id" not in outside


def test_fake_key_is_redacted_everywhere(log_file: Path, token: str) -> None:
    log = structlog.get_logger()
    log.info("provider.call", api_key=FAKE_KEY, groq_key="anything", prompt_tokens=120)
    log.info(f"calling with {FAKE_KEY}", headers={"Authorization": f"Bearer {FAKE_KEY}"})
    log.info("nested", data=[{"note": f"key={FAKE_KEY}"}], session=f"token {token}")
    logging.getLogger("uvicorn.error").info("stdlib %s", FAKE_KEY)
    try:
        raise RuntimeError(f"failed with {FAKE_KEY} and {token}")
    except RuntimeError:
        log.exception("boom")

    raw = log_file.read_text(encoding="utf-8")
    assert FAKE_KEY not in raw
    assert token not in raw
    lines = read_lines(log_file)
    assert lines[0]["api_key"] == REDACTED
    assert lines[0]["groq_key"] == REDACTED
    assert lines[0]["prompt_tokens"] == 120  # counters are not secrets
    assert lines[1]["headers"]["Authorization"] == REDACTED
    assert lines[2]["data"] == [{"note": f"key={REDACTED}"}]
    assert "RuntimeError" in lines[4]["exception"]


@pytest.mark.parametrize(
    "text",
    [
        "sk-proj-AbCdEf0123456789",
        "gsk_AbCdEf0123456789xyz",
        "AIzaSyA-0123456789abcdefghijklmnop",
        "Bearer abc.def-ghi",
        "bearer abc123==",
    ],
)
def test_redactor_patterns(text: str) -> None:
    assert Redactor().redact_text(f"value: {text} end") == f"value: {REDACTED} end"


@pytest.mark.parametrize("text", ["task-scheduler", "ask-me", "the key is in the drawer"])
def test_redactor_keeps_ordinary_text(text: str) -> None:
    assert Redactor().redact_text(text) == text


def test_rotation_settings(log_file: Path) -> None:
    handlers = [
        h
        for h in logging.getLogger().handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    assert len(handlers) == 1
    assert handlers[0].maxBytes == LOG_FILE_MAX_BYTES == 5 * 1024 * 1024
    assert handlers[0].backupCount + 1 == LOG_FILE_BACKUPS + 1 == 5
    assert Path(handlers[0].baseFilename) == log_file


def test_rotation_happens(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("assistant_prof.core.logging.LOG_FILE_MAX_BYTES", 2_000)
    path = tmp_path / "rot.log"
    configure_logging(path)
    for i in range(200):
        structlog.get_logger().info("filler", i=i, pad="x" * 50)
    reset_logging()
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == ["rot.log", "rot.log.1", "rot.log.2", "rot.log.3", "rot.log.4"]


def test_stderr_copy_only_when_requested(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging(tmp_path / "a.log")
    structlog.get_logger().info("file only")
    assert capsys.readouterr() == ("", "")

    configure_logging(tmp_path / "b.log", to_stderr=True, secrets=["s3cret-value"])
    structlog.get_logger().info("both", note="s3cret-value")
    out, err = capsys.readouterr()
    assert out == ""  # stdout is reserved for the startup handshake
    assert json.loads(err)["note"] == REDACTED
    assert read_lines(tmp_path / "b.log")[0]["event"] == "both"


def test_reconfigure_replaces_own_handlers_only(tmp_path: Path) -> None:
    foreign = logging.NullHandler()
    root = logging.getLogger()
    root.addHandler(foreign)
    try:
        configure_logging(tmp_path / "a.log")
        configure_logging(tmp_path / "b.log")
        assert foreign in root.handlers
        assert sum(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers) == 1
        reset_logging()
        assert not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers)
    finally:
        root.removeHandler(foreign)
