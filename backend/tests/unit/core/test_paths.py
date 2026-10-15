import os
import sys
from pathlib import Path

import pytest

from assistant_prof.core.paths import APP_DIR_NAME, DataPaths, default_data_dir


def test_default_data_dir_is_per_user() -> None:
    path = default_data_dir()
    assert path.name == APP_DIR_NAME
    if sys.platform == "win32":
        assert path.parent == Path(os.environ["APPDATA"])


def test_resolve_uses_default_without_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("assistant_prof.core.paths.default_data_dir", lambda: tmp_path / "x")
    assert DataPaths.resolve().root == (tmp_path / "x").resolve()


def test_resolve_override_is_absolute(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    paths = DataPaths.resolve(Path("data"))
    assert paths.root == tmp_path.resolve() / "data"


def test_layout_and_ensure(tmp_path: Path) -> None:
    paths = DataPaths.resolve(tmp_path / "root")
    paths.ensure()
    paths.ensure()  # idempotent
    for directory in (paths.logs, paths.db, paths.workspaces, paths.templates):
        assert directory.is_dir()
        assert directory.parent == paths.root
    assert paths.log_file.parent == paths.logs
    assert paths.database == paths.db / "assistant.sqlite"
    assert paths.db_backups.parent == paths.db
