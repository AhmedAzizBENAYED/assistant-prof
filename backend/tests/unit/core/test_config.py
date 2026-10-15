from pathlib import Path

import pytest
from pydantic import SecretStr

from assistant_prof.core.config import (
    DEFAULT_CORS_ORIGINS,
    DEFAULT_DEV_ORIGIN,
    Settings,
    load_settings,
)
from assistant_prof.core.errors import ConfigError


def test_reads_environment(monkeypatch: pytest.MonkeyPatch, token: str, tmp_path: Path) -> None:
    monkeypatch.setenv("ASSISTANT_PROF_TOKEN", token)
    monkeypatch.setenv("ASSISTANT_PROF_PORT", "8123")
    monkeypatch.setenv("ASSISTANT_PROF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ASSISTANT_PROF_LOG_LEVEL", "DEBUG")
    settings = load_settings({}, frozen=False)
    assert settings.token.get_secret_value() == token
    assert settings.port == 8123
    assert settings.data_dir == tmp_path
    assert settings.log_level == "DEBUG"
    assert settings.dev is False


def test_overrides_win_over_environment(monkeypatch: pytest.MonkeyPatch, token: str) -> None:
    monkeypatch.setenv("ASSISTANT_PROF_TOKEN", token)
    monkeypatch.setenv("ASSISTANT_PROF_PORT", "8123")
    assert load_settings({"port": 9000}, frozen=False).port == 9000


def test_port_zero_is_the_default(token: str) -> None:
    assert Settings(token=SecretStr(token)).port == 0


@pytest.mark.parametrize("port", [-1, 65536])
def test_port_out_of_range(token: str, port: int, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSISTANT_PROF_TOKEN", token)
    with pytest.raises(ConfigError, match="port"):
        load_settings({"port": port}, frozen=False)


def test_missing_token() -> None:
    with pytest.raises(ConfigError, match="token: Field required"):
        load_settings({"port": 0}, frozen=False)


def test_short_token_is_rejected_without_echoing_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSISTANT_PROF_TOKEN", "too-short-secret")
    with pytest.raises(ConfigError, match="at least 32") as excinfo:
        load_settings({}, frozen=False)
    assert "too-short-secret" not in str(excinfo.value)


def test_token_is_hidden_in_repr(token: str) -> None:
    settings = Settings(token=SecretStr(token))
    assert token not in repr(settings)
    assert token not in str(settings.model_dump())


def test_settings_are_immutable(token: str) -> None:
    settings = Settings(token=SecretStr(token))
    with pytest.raises(ValueError, match="frozen"):
        settings.port = 1


def test_cors_origins_default_and_dev(token: str) -> None:
    prod = Settings(token=SecretStr(token))
    assert prod.allowed_origins == DEFAULT_CORS_ORIGINS
    assert DEFAULT_DEV_ORIGIN not in prod.allowed_origins
    dev = Settings(token=SecretStr(token), dev=True)
    assert dev.allowed_origins == (*DEFAULT_CORS_ORIGINS, DEFAULT_DEV_ORIGIN)


def test_cors_origins_from_environment(monkeypatch: pytest.MonkeyPatch, token: str) -> None:
    monkeypatch.setenv("ASSISTANT_PROF_TOKEN", token)
    monkeypatch.setenv("ASSISTANT_PROF_CORS_ORIGINS", '["http://tauri.localhost"]')
    assert load_settings({}, frozen=False).allowed_origins == ("http://tauri.localhost",)


def test_dev_mode_refused_when_frozen(monkeypatch: pytest.MonkeyPatch, token: str) -> None:
    monkeypatch.setenv("ASSISTANT_PROF_TOKEN", token)
    with pytest.raises(ConfigError, match="packaged"):
        load_settings({"dev": True}, frozen=True)
    assert load_settings({}, frozen=True).dev is False
