"""Location of the user data directory and its layout (ARCHITECTURE §7.9)."""

from dataclasses import dataclass
from pathlib import Path

import platformdirs

APP_DIR_NAME = "AssistantProf"
LOG_FILE_NAME = "assistant-prof.log"
DATABASE_FILE_NAME = "assistant.sqlite"


def default_data_dir() -> Path:
    """Return the per-user data directory (``%APPDATA%/AssistantProf`` on Windows)."""
    return Path(platformdirs.user_data_dir(APP_DIR_NAME, appauthor=False, roaming=True))


@dataclass(frozen=True)
class DataPaths:
    """Paths inside the data directory."""

    root: Path

    @classmethod
    def resolve(cls, override: Path | None = None) -> "DataPaths":
        """Use ``override`` when given (tests, desktop shell), else the platform default."""
        root = override if override is not None else default_data_dir()
        return cls(root.expanduser().resolve())

    @property
    def logs(self) -> Path:
        """Directory of the rotating log files."""
        return self.root / "logs"

    @property
    def log_file(self) -> Path:
        """Active log file."""
        return self.logs / LOG_FILE_NAME

    @property
    def db(self) -> Path:
        """Directory of the SQLite files."""
        return self.root / "db"

    @property
    def database(self) -> Path:
        """Application database (SQLAlchemy + Alembic, ADR-028)."""
        return self.db / DATABASE_FILE_NAME

    @property
    def db_backups(self) -> Path:
        """Copies of the database taken before each migration (ADR-040)."""
        return self.db / "backups"

    @property
    def workspaces(self) -> Path:
        """One sub-directory per imported document."""
        return self.root / "workspaces"

    @property
    def templates(self) -> Path:
        """One sub-directory per learned template."""
        return self.root / "templates"

    def ensure(self) -> None:
        """Create the directory tree if missing."""
        for directory in (self.root, self.logs, self.db, self.workspaces, self.templates):
            directory.mkdir(parents=True, exist_ok=True)
