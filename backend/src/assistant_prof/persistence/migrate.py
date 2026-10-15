"""Bring ``assistant.sqlite`` to the latest schema at startup (ADR-040).

Fast path: the stored revision is read with ``sqlite3``; when it equals ``HEAD_REVISION`` nothing
else happens, and neither Alembic nor SQLAlchemy is imported (they cost about 0.4 s and 30 MB at
startup). A test keeps ``HEAD_REVISION`` equal to the head of the migration scripts.

An existing database whose revision is behind head is first copied with SQLite's backup API to
``db/backups/assistant-<old revision>-<UTC timestamp>.sqlite``; the ``BACKUPS_KEPT`` most recent
copies are kept. A new database, or one already at head, is not copied.

Migrations run in one transaction with foreign keys off (SQLite's procedure for schema changes:
table rebuilds would otherwise fire ``ON DELETE`` actions), followed by
``PRAGMA foreign_key_check``. Any failure raises ``DatabaseError``; the entry point then exits
with code 3.
"""

import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import structlog

from assistant_prof.core.clock import Clock
from assistant_prof.core.errors import DatabaseError

HEAD_REVISION = "0001"  # update with every new revision; checked by a test
MIGRATIONS_DIR = Path(__file__).parent / "migrations"
BACKUPS_KEPT = 3
_BACKUP_PREFIX = "assistant-"
_STAMP_FORMAT = "%Y%m%dT%H%M%S%fZ"  # fixed width, so names sort by time

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class MigrationResult:
    """What ``upgrade_to_head`` did."""

    from_revision: str | None
    to_revision: str
    backup: Path | None


def read_revision(path: Path) -> str | None:
    """Return the Alembic revision stored in ``path``; ``None`` if missing or never migrated."""
    if not path.exists():
        return None
    with closing(sqlite3.connect(path)) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'alembic_version'"
        ).fetchone()
        if table is None:
            return None
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    return None if row is None else str(row[0])


def head_revision(script_location: Path = MIGRATIONS_DIR) -> str:
    """Return the head revision of the migration scripts (imports Alembic)."""
    from alembic.script import ScriptDirectory

    head = ScriptDirectory(str(script_location)).get_current_head()
    if head is None:
        raise DatabaseError("no migration scripts found")
    return head


def backup_database(path: Path, backups_dir: Path, revision: str, now: datetime) -> Path:
    """Copy ``path`` into ``backups_dir`` with the backup API, then keep the newest copies."""
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.astimezone(UTC).strftime(_STAMP_FORMAT)
    target = backups_dir / f"{_BACKUP_PREFIX}{revision}-{stamp}.sqlite"
    with closing(sqlite3.connect(path)) as source, closing(sqlite3.connect(target)) as copy:
        source.backup(copy)
    prune_backups(backups_dir, BACKUPS_KEPT)
    return target


def prune_backups(backups_dir: Path, keep: int) -> list[Path]:
    """Delete all but the ``keep`` most recent backups; return the deleted paths."""
    backups = sorted(
        backups_dir.glob(f"{_BACKUP_PREFIX}*.sqlite"),
        key=lambda backup: backup.stem.rsplit("-", 1)[-1],
    )
    removed = backups[:-keep] if keep > 0 else backups
    for backup in removed:
        backup.unlink()
    return removed


def upgrade_to_head(
    path: Path,
    backups_dir: Path,
    clock: Clock,
    *,
    script_location: Path = MIGRATIONS_DIR,
    known_head: str | None = HEAD_REVISION,
) -> MigrationResult:
    """Migrate the database at ``path`` to head, taking a backup first when it is outdated.

    ``known_head`` enables the fast path; ``None`` always asks Alembic (tests with other scripts).
    """
    try:
        current = read_revision(path)
        if current is not None and current == known_head:
            return MigrationResult(current, current, None)
        return _migrate(path, backups_dir, clock, script_location, current)
    except (sqlite3.Error, OSError) as exc:
        raise _failure(path, exc) from exc


def _migrate(
    path: Path, backups_dir: Path, clock: Clock, script_location: Path, current: str | None
) -> MigrationResult:
    # Imported here so a database already at head never loads them (fast path).
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.script.revision import RevisionError
    from alembic.util import CommandError
    from sqlalchemy.exc import SQLAlchemyError

    from assistant_prof.persistence.db import create_sqlite_engine

    try:
        head = head_revision(script_location)
        if current == head:
            return MigrationResult(current, head, None)

        backup = None
        if current is not None:
            # Refuse a revision this build does not know (database written by a newer version).
            ScriptDirectory(str(script_location)).get_revision(current)
            backup = backup_database(path, backups_dir, current, clock.now())

        config = Config(stdout=sys.stderr)  # the default is bound to the real stdout at import
        config.set_main_option("script_location", str(script_location).replace("%", "%%"))
        engine = create_sqlite_engine(path, foreign_keys=False)
        try:
            # One transaction for the whole upgrade: any failure leaves the file unchanged.
            with engine.begin() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
                violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise DatabaseError(
                        f"migration left {len(violations)} foreign key violation(s)"
                    )
        finally:
            engine.dispose()
    except (SQLAlchemyError, CommandError, RevisionError) as exc:
        raise _failure(path, exc) from exc

    log.info(
        "database.migrated",
        from_revision=current,
        to_revision=head,
        backup=backup.name if backup is not None else None,
    )
    return MigrationResult(current, head, backup)


def _failure(path: Path, exc: Exception) -> DatabaseError:
    return DatabaseError(f"cannot open or migrate {path.name}: {_describe(exc)}")


def _describe(exc: Exception) -> str:
    """Short English cause, without SQL statements or parameters."""
    orig = getattr(exc, "orig", None)  # SQLAlchemy's DBAPIError wraps the driver error
    if isinstance(orig, sqlite3.Error):
        exc = orig
    elif type(exc).__module__.startswith("sqlalchemy."):
        return type(exc).__name__  # its message embeds the SQL statement
    return f"{type(exc).__name__}: {exc}"
