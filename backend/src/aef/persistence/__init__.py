"""Persistence layer — :class:`StorageAdapter` Protocol + SQLite implementation.

# ADR: Persistence — SQLite Default, Postgres Swap-In
# See: adr/0006-persistence-sqlite-default-postgres-swap-in.md
"""

from __future__ import annotations

from aef.persistence.base import StorageAdapter, redact_secrets
from aef.persistence.session import (
    create_async_engine_for,
    create_session_factory,
    install_sqlite_pragmas,
)
from aef.persistence.sqlite import SQLiteStorage

__all__ = [
    "SQLiteStorage",
    "StorageAdapter",
    "create_async_engine_for",
    "create_session_factory",
    "install_sqlite_pragmas",
    "redact_secrets",
]
