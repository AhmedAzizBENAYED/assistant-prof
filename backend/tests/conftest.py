import os
import secrets
from collections.abc import Iterator

import pytest
import structlog

from assistant_prof.core.logging import reset_logging


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Hide the developer's ASSISTANT_PROF_* variables and undo logging configuration."""
    for name in list(os.environ):
        if name.startswith("ASSISTANT_PROF_"):
            monkeypatch.delenv(name)
    yield
    reset_logging()
    structlog.reset_defaults()


@pytest.fixture
def token() -> str:
    return secrets.token_urlsafe(32)
