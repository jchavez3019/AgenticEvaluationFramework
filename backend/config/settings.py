"""Strongly-typed settings derived from the environment.

Modules that need configuration call :func:`get_settings` rather than
reading ``os.environ`` directly. Tests can patch the settings via
:func:`reset_settings` to restore default values between cases.

# ADR: Persistence — SQLite Default, Postgres Swap-In
# See: adr/0006-persistence-sqlite-default-postgres-swap-in.md
# ADR: Logging and Telemetry Contract
# See: adr/0012-logging-and-telemetry-contract.md
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-level configuration loaded from environment variables.

    All env-driven settings exposed by the framework live here. Each
    field is annotated with a default that matches the documented
    behaviour from the relevant ADR; the env var name is the field name
    upper-cased and prefixed with ``AEF_``.

    * model_config: Pydantic-settings config — env prefix, optional ``.env`` file, frozen.
    * database_url: SQLAlchemy async URL (SQLite by default; Postgres per ADR-0006).
    * database_auto_upgrade: When ``True``, run Alembic migrations on startup.
    * database_echo: When ``True``, echo SQL statements to the log (debug only).
    * api_log_path: Filesystem path for the API server's rotating log file.
    """

    model_config = SettingsConfigDict(
        env_prefix="AEF_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    database_url: str = Field(
        default="sqlite+aiosqlite:///./.aef/aef.sqlite3",
        description=(
            "SQLAlchemy async URL — SQLite by default; " "Postgres swap is documented in ADR-0006."
        ),
    )
    database_auto_upgrade: bool = Field(
        default=True,
        description="When True, run `alembic upgrade head` on startup (per ADR-0006 §6).",
    )
    database_echo: bool = Field(
        default=False,
        description="Toggle SQLAlchemy echo logging — useful for debugging only.",
    )
    api_log_path: Path = Field(
        default=Path("outputs/frontend/server.log"),
        description="Where the API server's rotating log file is written (per ADR-0006 §7).",
    )


@lru_cache(maxsize=1)
def _cached_settings() -> Settings:
    """
    Return cached :class:`Settings` (LRU-backed).

    :return: A :class:`Settings` instance.
    """
    return Settings()


def get_settings() -> Settings:
    """
    Return the process-wide :class:`Settings` (cached on first call).

    :return: :class:`Settings` instance.
    """
    return _cached_settings()


def reset_settings() -> None:
    """
    Drop the cached :class:`Settings` so the next call rereads env vars.

    Tests use this to point :func:`get_settings` at a temporary database URL or log path
    without leaking state between cases.
    """
    _cached_settings.cache_clear()
