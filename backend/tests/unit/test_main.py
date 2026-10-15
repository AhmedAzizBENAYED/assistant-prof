import io
import json
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

import assistant_prof
from assistant_prof import main as main_module
from assistant_prof.core.config import Settings
from assistant_prof.main import build_parser, main, ready_line, serve


def test_ready_line_format() -> None:
    line = ready_line(51234)
    assert line == f'{{"event":"ready","port":51234,"version":"{assistant_prof.__version__}"}}'
    assert json.loads(line) == {
        "event": "ready",
        "port": 51234,
        "version": assistant_prof.__version__,
    }


def test_parser_requires_port_and_has_no_token_argument(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    assert parser.parse_args(["--port", "0"]).port == 0
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["--port", "0", "--token", "x" * 40])
    capsys.readouterr()


def test_missing_token_exits_with_config_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--port", "0"]) == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert "token" in err


def test_short_token_is_not_echoed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ASSISTANT_PROF_TOKEN", "short-but-secret")
    assert main(["--port", "0"]) == 2
    assert "short-but-secret" not in capsys.readouterr().err


def test_dev_refused_in_frozen_build(
    monkeypatch: pytest.MonkeyPatch, token: str, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ASSISTANT_PROF_TOKEN", token)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert main(["--port", "0", "--dev"]) == 2
    assert "packaged" in capsys.readouterr().err


def test_main_wires_settings_paths_and_stdout(
    monkeypatch: pytest.MonkeyPatch,
    token: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ASSISTANT_PROF_TOKEN", token)
    seen: dict[str, object] = {}

    def fake_serve(settings: Settings, handshake: io.TextIOBase | None) -> None:
        seen["settings"] = settings
        print("stray print")  # noqa: T201  # must not reach stdout
        assert handshake is not None
        handshake.write(ready_line(4321) + "\n")

    real_stdout = sys.stdout
    monkeypatch.setattr(main_module, "serve", fake_serve)
    assert main(["--port", "0", "--data-dir", str(tmp_path / "data"), "--dev"]) == 0
    assert sys.stdout is real_stdout

    settings = seen["settings"]
    assert isinstance(settings, Settings)
    assert settings.dev is True
    assert settings.port == 0
    assert (tmp_path / "data" / "logs" / "assistant-prof.log").is_file()
    out, err = capsys.readouterr()
    assert out == ready_line(4321) + "\n"
    assert "stray print" in err
    assert token not in err


def test_serve_announces_actual_port_and_stops(token: str, tmp_path: Path) -> None:
    handshake = io.StringIO()
    settings = Settings(token=SecretStr(token), port=0)
    thread = threading.Thread(target=serve, args=(settings, handshake), daemon=True)
    thread.start()

    deadline = time.monotonic() + 20
    while not handshake.getvalue() and time.monotonic() < deadline:
        time.sleep(0.05)
    ready = json.loads(handshake.getvalue())
    assert ready["event"] == "ready"
    port = ready["port"]
    assert port > 0

    headers = {"X-Session-Token": token}
    base = f"http://127.0.0.1:{port}"
    assert httpx.get(f"{base}/health", headers=headers).json()["status"] == "ok"
    assert httpx.post(f"{base}/shutdown", headers=headers).status_code == 202
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert handshake.getvalue().count("\n") == 1
