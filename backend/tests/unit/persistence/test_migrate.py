import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy.exc import OperationalError

from assistant_prof.core.clock import FakeClock
from assistant_prof.core.errors import DatabaseError
from assistant_prof.persistence import migrate
from assistant_prof.persistence.db import create_sqlite_engine
from assistant_prof.persistence.migrate import (
    BACKUPS_KEPT,
    HEAD_REVISION,
    MIGRATIONS_DIR,
    backup_database,
    head_revision,
    read_revision,
    upgrade_to_head,
)
from assistant_prof.persistence.models import Base

BASE_TABLES = {"settings", "documents", "versions"}

# A test-only revision on top of the real head, which makes a database at head outdated.
EXTRA_REVISION = '''"""Test-only revision."""

import sqlalchemy as sa
from alembic import op

revision = "9001"
down_revision = "{down}"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("extra", sa.Column("id", sa.Integer(), primary_key=True))
    {more}


def downgrade() -> None:
    op.drop_table("extra")
'''


def _tables(path: Path) -> set[str]:
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        return {name for (name,) in rows}


def _scripts_with_extra_revision(tmp_path: Path, more: str = "pass") -> Path:
    scripts = tmp_path / "scripts"
    shutil.copytree(MIGRATIONS_DIR, scripts, ignore=shutil.ignore_patterns("__pycache__"))
    revision = EXTRA_REVISION.format(down=head_revision(), more=more)
    (scripts / "versions" / "r9001_extra.py").write_text(revision, encoding="utf-8")
    return scripts


def _cli_config(db_path: Path) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    return config


@pytest.fixture
def backups(tmp_path: Path) -> Path:
    return tmp_path / "backups"


@pytest.fixture
def db_dir(db_path: Path) -> Path:
    db_path.parent.mkdir(parents=True)
    return db_path.parent


@pytest.mark.usefixtures("db_dir")
def test_empty_database_upgrades_from_zero_to_head(
    db_path: Path, backups: Path, clock: FakeClock
) -> None:
    result = upgrade_to_head(db_path, backups, clock)
    assert result.from_revision is None
    assert result.to_revision == head_revision() == read_revision(db_path)
    assert result.backup is None
    assert _tables(db_path) == BASE_TABLES | {"alembic_version"}
    assert not backups.exists()  # nothing to back up in a new database


def test_head_revision_constant_matches_the_scripts() -> None:
    assert head_revision() == HEAD_REVISION


@pytest.mark.usefixtures("db_dir")
@pytest.mark.parametrize("known_head", [HEAD_REVISION, None], ids=["fast-path", "alembic"])
def test_database_at_head_is_left_alone(
    db_path: Path, backups: Path, clock: FakeClock, known_head: str | None
) -> None:
    upgrade_to_head(db_path, backups, clock)
    result = upgrade_to_head(db_path, backups, clock, known_head=known_head)
    assert result.from_revision == result.to_revision == HEAD_REVISION
    assert result.backup is None
    assert not backups.exists()


@pytest.mark.usefixtures("db_dir")
def test_startup_at_head_imports_neither_alembic_nor_sqlalchemy(
    db_path: Path, backups: Path, clock: FakeClock
) -> None:
    upgrade_to_head(db_path, backups, clock)
    script = "\n".join(
        [
            "import sys",
            "from pathlib import Path",
            "import assistant_prof.main",
            "from assistant_prof.core.clock import SystemClock",
            "from assistant_prof.persistence.migrate import upgrade_to_head",
            "upgrade_to_head(Path(sys.argv[1]), Path(sys.argv[2]), SystemClock())",
            "print(sorted(m for m in ('alembic', 'sqlalchemy') if m in sys.modules))",
        ]
    )
    # A fresh interpreter, since this one has imported both already.
    result = subprocess.run(  # noqa: S603  # fixed command, test-controlled arguments
        [sys.executable, "-c", script, str(db_path), str(backups)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "[]"


@pytest.mark.usefixtures("db_dir")
def test_models_match_the_migrations(db_path: Path, backups: Path, clock: FakeClock) -> None:
    upgrade_to_head(db_path, backups, clock)
    engine = create_sqlite_engine(db_path)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={"compare_type": True})
            assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()


@pytest.mark.usefixtures("db_dir")
def test_downgrade_to_base_and_back_through_the_cli_environment(db_path: Path) -> None:
    config = _cli_config(db_path)
    command.upgrade(config, "head")
    assert _tables(db_path) == BASE_TABLES | {"alembic_version"}
    command.downgrade(config, "base")
    assert _tables(db_path) == {"alembic_version"}
    assert read_revision(db_path) is None
    command.upgrade(config, "head")
    assert read_revision(db_path) == head_revision()


def test_cli_environment_refuses_other_urls_and_offline_mode(tmp_path: Path) -> None:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", "postgresql://localhost/x")
    with pytest.raises(RuntimeError, match="only sqlite"):
        command.upgrade(config, "head")
    with pytest.raises(RuntimeError, match="offline"):
        command.upgrade(_cli_config(tmp_path / "x.sqlite"), "head", sql=True)


@pytest.mark.usefixtures("db_dir")
def test_outdated_database_gets_exactly_one_backup_with_the_old_content(
    tmp_path: Path, db_path: Path, backups: Path, clock: FakeClock
) -> None:
    old = upgrade_to_head(db_path, backups, clock).to_revision
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute(
            "INSERT INTO settings VALUES ('theme', '\"clair\"', '2026-01-01 00:00:00')"
        )

    scripts = _scripts_with_extra_revision(tmp_path)
    result = upgrade_to_head(db_path, backups, clock, script_location=scripts, known_head=None)

    assert (result.from_revision, result.to_revision) == (old, "9001")
    assert result.backup is not None
    assert list(backups.iterdir()) == [result.backup]
    assert result.backup.name == f"assistant-{old}-20260101T000000000000Z.sqlite"
    assert read_revision(result.backup) == old
    assert "extra" not in _tables(result.backup)
    with closing(sqlite3.connect(result.backup)) as connection:
        assert connection.execute("SELECT value FROM settings").fetchall() == [('"clair"',)]
    assert read_revision(db_path) == "9001"
    assert "extra" in _tables(db_path)


def test_fourth_backup_removes_the_oldest(tmp_path: Path, backups: Path, clock: FakeClock) -> None:
    source = tmp_path / "source.sqlite"
    with closing(sqlite3.connect(source)) as connection:
        connection.execute("CREATE TABLE t (x)")
    made: list[Path] = []
    # Revisions do not sort like times: the order must come from the timestamp.
    for revision in ("0009", "0003", "0007", "0001"):
        made.append(backup_database(source, backups, revision, clock.now()))
        clock.advance(1)
    assert BACKUPS_KEPT == 3
    assert sorted(backups.iterdir()) == sorted(made[1:])
    assert not made[0].exists()


@pytest.mark.usefixtures("db_dir")
def test_unknown_revision_is_refused_before_any_backup(
    db_path: Path, backups: Path, clock: FakeClock
) -> None:
    upgrade_to_head(db_path, backups, clock)
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute("UPDATE alembic_version SET version_num = 'from-the-future'")
    with pytest.raises(DatabaseError, match=r"cannot open or migrate assistant\.sqlite"):
        upgrade_to_head(db_path, backups, clock)
    assert not backups.exists()


@pytest.mark.usefixtures("db_dir")
def test_corrupt_file_raises_database_error(db_path: Path, backups: Path, clock: FakeClock) -> None:
    db_path.write_bytes(b"this is not a database" * 100)
    with pytest.raises(DatabaseError, match="file is not a database"):
        upgrade_to_head(db_path, backups, clock)


@pytest.mark.usefixtures("db_dir")
def test_foreign_key_violation_rolls_the_whole_migration_back(
    tmp_path: Path, db_path: Path, backups: Path, clock: FakeClock
) -> None:
    old = upgrade_to_head(db_path, backups, clock).to_revision
    orphan = (
        'op.execute("INSERT INTO versions (id, document_id, number, created_at) '
        "VALUES ('v', 'missing', 1, '2026-01-01 00:00:00')\")"
    )
    scripts = _scripts_with_extra_revision(tmp_path, more=orphan)
    with pytest.raises(DatabaseError, match="1 foreign key violation"):
        upgrade_to_head(db_path, backups, clock, script_location=scripts, known_head=None)
    assert read_revision(db_path) == old
    assert "extra" not in _tables(db_path)  # the DDL was rolled back too
    assert len(list(backups.iterdir())) == 1  # the backup taken before is kept


def test_scripts_without_revisions_have_no_head(tmp_path: Path) -> None:
    (tmp_path / "versions").mkdir()
    with pytest.raises(DatabaseError, match="no migration scripts"):
        head_revision(tmp_path)


def test_errors_are_described_without_sql_statements() -> None:
    wrapped = OperationalError("SELECT secret FROM t", {}, sqlite3.OperationalError("locked"))
    assert migrate._describe(wrapped) == "OperationalError: locked"
    bare = OperationalError("SELECT secret FROM t", {}, Exception("x"))
    assert migrate._describe(bare) == "OperationalError"
    assert migrate._describe(OSError("disk full")) == "OSError: disk full"


def test_files_without_alembic_version_have_no_revision(tmp_path: Path) -> None:
    assert read_revision(tmp_path / "missing.sqlite") is None
    other = tmp_path / "other.sqlite"
    with closing(sqlite3.connect(other)) as connection:
        connection.execute("CREATE TABLE t (x)")
    assert read_revision(other) is None
