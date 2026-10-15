from collections.abc import Iterator
from pathlib import Path

import pytest

from assistant_prof.core.clock import FakeClock
from assistant_prof.persistence.db import Database
from assistant_prof.persistence.migrate import upgrade_to_head


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "db" / "assistant.sqlite"


@pytest.fixture
def database(db_path: Path, clock: FakeClock) -> Iterator[Database]:
    """A database migrated to head on a temporary file."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    upgrade_to_head(db_path, db_path.parent / "backups", clock)
    database = Database(db_path)
    yield database
    database.dispose()
