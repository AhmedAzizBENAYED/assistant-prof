"""Alembic environment (ADR-040).

At startup, ``persistence.migrate`` passes its own connection (foreign keys off) in
``config.attributes["connection"]``. The developer CLI (``backend/alembic.ini``) has no
connection, so one is opened on ``sqlalchemy.url``. Offline (``--sql``) mode is not supported.
"""

from pathlib import Path

from alembic import context
from sqlalchemy import Connection

from assistant_prof.persistence.db import create_sqlite_engine
from assistant_prof.persistence.models import Base


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=True,  # SQLite can only alter tables by rebuilding them
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_from_cli(url: str) -> None:
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise RuntimeError(f"only {prefix}<path> URLs are supported")
    engine = create_sqlite_engine(Path(url.removeprefix(prefix)), foreign_keys=False)
    try:
        with engine.begin() as connection:
            _run(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("offline (--sql) migrations are not supported")
_connection = context.config.attributes.get("connection")
if _connection is not None:
    _run(_connection)
else:
    _run_from_cli(context.config.get_main_option("sqlalchemy.url") or "")
