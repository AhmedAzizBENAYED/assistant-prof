import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from sqlalchemy import select

from assistant_prof.core.clock import FakeClock
from assistant_prof.persistence.db import BUSY_TIMEOUT_MS, Database, create_sqlite_engine
from assistant_prof.persistence.models import SettingRow
from assistant_prof.persistence.repositories import SettingsRepository


def _pragmas(database: Database) -> dict[str, object]:
    with database.engine.connect() as connection:
        return {
            name: connection.exec_driver_sql(f"PRAGMA {name}").scalar()
            for name in ("journal_mode", "synchronous", "foreign_keys", "busy_timeout")
        }


def test_every_connection_uses_wal_full_sync_and_foreign_keys(database: Database) -> None:
    assert _pragmas(database) == {
        "journal_mode": "wal",
        "synchronous": 2,  # FULL
        "foreign_keys": 1,
        "busy_timeout": BUSY_TIMEOUT_MS,
    }


def test_wal_is_set_even_on_a_file_created_in_another_mode(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("CREATE TABLE t (x)")
    database = Database(path)
    try:
        assert _pragmas(database)["journal_mode"] == "wal"
    finally:
        database.dispose()


def test_migration_engine_turns_foreign_keys_off(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "x.sqlite", foreign_keys=False)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 0
    finally:
        engine.dispose()


def _read_theme(database: Database) -> object:
    with database.session() as session:
        return session.scalar(select(SettingRow.value).where(SettingRow.key == "theme"))


def test_reader_is_not_blocked_by_an_open_write_transaction(
    database: Database, clock: FakeClock
) -> None:
    with database.session() as session:
        SettingsRepository(session, clock).set("theme", "clair")

    with database.session() as writer:
        SettingsRepository(writer, clock).set("theme", "sombre")  # flushed, not committed
        assert _read_theme(database) == "clair"  # readers see the last committed value
    assert _read_theme(database) == "sombre"


def test_writer_commits_while_a_reader_holds_a_snapshot(
    database: Database, clock: FakeClock
) -> None:
    with database.session() as session:
        SettingsRepository(session, clock).set("theme", "clair")

    with database.session() as reader:
        query = select(SettingRow.value).where(SettingRow.key == "theme")
        assert reader.scalar(query) == "clair"
        # In rollback-journal mode this commit would wait for the reader and fail as locked.
        with database.session() as writer:
            SettingsRepository(writer, clock).set("theme", "sombre")
        assert reader.scalar(query) == "clair"  # the reader keeps its snapshot
    assert _read_theme(database) == "sombre"


def test_session_rolls_back_on_exception(database: Database, clock: FakeClock) -> None:
    def failing_unit_of_work() -> None:
        with database.session() as session:
            SettingsRepository(session, clock).set("theme", "sombre")
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        failing_unit_of_work()
    assert _read_theme(database) is None
