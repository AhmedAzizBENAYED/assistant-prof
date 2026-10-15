"""Startup settings: environment (``ASSISTANT_PROF_*``) overridden by CLI arguments.

The session token is read from ``ASSISTANT_PROF_TOKEN`` only: command lines are visible to
other processes, so there is no ``--token`` argument (ADR-038).
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from assistant_prof.core.errors import ConfigError

TOKEN_MIN_LENGTH = 32
DEFAULT_CORS_ORIGINS = ("http://tauri.localhost", "https://tauri.localhost")
DEFAULT_DEV_ORIGIN = "http://localhost:5173"


class Settings(BaseSettings):
    """Validated backend settings. Host is not configurable: always 127.0.0.1."""

    model_config = SettingsConfigDict(env_prefix="ASSISTANT_PROF_", frozen=True)

    token: SecretStr = Field(min_length=TOKEN_MIN_LENGTH)
    port: int = Field(default=0, ge=0, le=65535, description="0 lets the OS pick a free port")
    data_dir: Path | None = None
    dev: bool = False
    exit_on_stdin_eof: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    dev_origin: str = DEFAULT_DEV_ORIGIN

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        """CORS origins in effect: the Vite dev origin is added only in dev mode."""
        if self.dev:
            return (*self.cors_origins, self.dev_origin)
        return self.cors_origins


def load_settings(overrides: Mapping[str, object], *, frozen: bool) -> Settings:
    """Build settings from the environment plus ``overrides`` (CLI values win).

    Raises ``ConfigError`` with an English message that never echoes input values,
    so the token cannot leak into stderr. ``frozen`` is true in packaged builds,
    which refuse dev mode.
    """
    try:
        settings = Settings(**overrides)  # type: ignore[arg-type]  # values validated by pydantic
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in err['loc']) or 'settings'}: {err['msg']}"
            for err in exc.errors(include_input=False, include_url=False)
        )
        raise ConfigError(f"invalid configuration: {problems}") from None
    if frozen and settings.dev:
        raise ConfigError("dev mode is not available in packaged builds")
    return settings
