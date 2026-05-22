"""Process-wide settings — environment-driven, typed, validated.

# ADR: Persistence — SQLite Default, Postgres Swap-In
# See: adr/0006-persistence-sqlite-default-postgres-swap-in.md
"""

from __future__ import annotations

from backend.config.settings import Settings, get_settings, reset_settings

__all__ = ["Settings", "get_settings", "reset_settings"]
