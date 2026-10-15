import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "dev_backend.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("dev_backend", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_starts_dev_backend_with_fresh_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    script = load_script()
    calls: list[tuple[Sequence[str], dict[str, str]]] = []

    def fake_call(cmd: Sequence[str], env: dict[str, str]) -> int:
        calls.append((cmd, env))
        return 3

    monkeypatch.setattr(script.subprocess, "call", fake_call)
    assert script.main(["--port", "8000"]) == 3
    assert script.main([]) == 3

    (cmd, env), (_, env2) = calls
    assert list(cmd[:3]) == [sys.executable, "-m", "assistant_prof"]
    assert list(cmd[3:5]) == ["--port", "0"]
    assert "--dev" in cmd
    assert list(cmd[-2:]) == ["--port", "8000"]  # last --port wins in argparse
    token = env["ASSISTANT_PROF_TOKEN"]
    assert len(token) >= 32
    assert token != env2["ASSISTANT_PROF_TOKEN"]
    out = capsys.readouterr().out
    assert out.count(token) == 1


def test_ctrl_c_exits_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    script = load_script()

    def interrupted(cmd: Sequence[str], env: dict[str, str]) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(script.subprocess, "call", interrupted)
    assert script.main([]) == 0
