"""Async session factory plus SQLite pragma installation.

The pragma installer is a SQLAlchemy ``connect`` event listener — we
need WAL mode, foreign-key enforcement, and ``synchronous=NORMAL`` to
match ADR-0006 §1, and these can only be set per-connection in SQLite.

# ADR: Persistence — SQLite Default, Postgres Swap-In
# See: adr/0006-persistence-sqlite-default-postgres-swap-in.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession as _AsyncSession,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def install_sqlite_pragmas(engine: AsyncEngine) -> None:
    """Wire WAL + FK + ``synchronous=NORMAL`` onto every SQLite connection.

    The function is a no-op for non-SQLite engines so the same call site
    works after a Postgres swap.
    """
    if not engine.url.get_backend_name().startswith("sqlite"):
        return

    def _on_connect(
        dbapi_connection: Any,
        _connection_record: Any,
    ) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()

    event.listen(engine.sync_engine, "connect", _on_connect)


def create_async_engine_for(
    url: str,
    *,
    echo: bool = False,
) -> AsyncEngine:
    """Build an :class:`AsyncEngine` and attach the SQLite pragma listener."""
    engine = create_async_engine(url, echo=echo, future=True)
    install_sqlite_pragmas(engine)
    return engine


def create_session_factory(
    engine: AsyncEngine,
) -> Callable[[], _AsyncSession]:
    """Return a parameterless async-session factory bound to ``engine``."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return factory
