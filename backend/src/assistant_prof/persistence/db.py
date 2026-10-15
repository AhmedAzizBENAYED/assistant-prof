"""SQLite engine and sessions for ``db/assistant.sqlite`` (ADR-028, ADR-040).

Every connection is set to WAL with ``synchronous=FULL``, foreign keys on and a busy timeout.
``journal_mode`` persists in the file, but it is set anyway so a file created elsewhere is fixed.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

BUSY_TIMEOUT_MS = 5000


def apply_pragmas(connection: sqlite3.Connection, *, foreign_keys: bool = True) -> None:
    """Set the per-connection pragmas; must run outside a transaction to take effect."""
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.execute(f"PRAGMA foreign_keys={'ON' if foreign_keys else 'OFF'}")
    connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")


def create_sqlite_engine(path: Path, *, foreign_keys: bool = True) -> Engine:
    """Return an engine on the SQLite file ``path``.

    ``foreign_keys=False`` is for migrations only: with foreign keys on, the table rebuilds of
    SQLite batch migrations would fire ``ON DELETE`` actions (ADR-040).
    """
    engine = create_engine(f"sqlite:///{path.as_posix()}")

    # The driver's legacy mode never emits BEGIN before SELECT or DDL, so reads would not see a
    # stable snapshot and migrations would not be atomic. Turn it off and emit BEGIN ourselves
    # (SQLAlchemy's documented recipe for pysqlite).
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: sqlite3.Connection, _record: Any) -> None:
        dbapi_connection.isolation_level = None
        apply_pragmas(dbapi_connection, foreign_keys=foreign_keys)

    @event.listens_for(engine, "begin")
    def _on_begin(connection: Connection) -> None:
        connection.exec_driver_sql("BEGIN")

    return engine


class Database:
    """Engine plus session factory; a session is one unit of work."""

    def __init__(self, path: Path) -> None:
        self.engine = create_sqlite_engine(path)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a session that commits on success and rolls back on any exception."""
        with self._sessions.begin() as session:
            yield session

    def dispose(self) -> None:
        """Close every pooled connection (required before moving or deleting the file)."""
        self.engine.dispose()
