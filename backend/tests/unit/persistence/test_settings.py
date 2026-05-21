"""Settings-loading unit tests."""

from __future__ import annotations

import pytest

from aef.config import Settings, get_settings, reset_settings


@pytest.fixture(autouse=True)
def reset_settings_cache() -> None:
    reset_settings()


def test_default_database_url() -> None:
    settings = Settings()
    assert "sqlite+aiosqlite" in settings.database_url
    assert settings.database_auto_upgrade is True
    assert settings.database_echo is False


def test_environment_overrides_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AEF_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("AEF_DATABASE_AUTO_UPGRADE", "false")
    settings = Settings()
    assert settings.database_url == "sqlite+aiosqlite:///:memory:"
    assert settings.database_auto_upgrade is False


def test_get_settings_is_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AEF_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    first = get_settings()
    monkeypatch.setenv("AEF_DATABASE_URL", "sqlite+aiosqlite:///./other.sqlite3")
    second = get_settings()
    assert first is second
    reset_settings()
    third = get_settings()
    assert third.database_url == "sqlite+aiosqlite:///./other.sqlite3"
