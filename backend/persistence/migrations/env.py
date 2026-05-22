"""Alembic env script — wires the AEF SQLAlchemy metadata into Alembic.

Imported by ``alembic upgrade``/``downgrade``/``revision`` commands.

# ADR: Persistence — SQLite Default, Postgres Swap-In
# See: adr/0006-persistence-sqlite-default-postgres-swap-in.md
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import TYPE_CHECKING

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from backend.config import get_settings
from backend.persistence.orm import Base
from backend.persistence.session import install_sqlite_pragmas

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emits SQL, no DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    Sync portion of the online migration — Alembic dispatches here.

    :param connection: Database connection used for migrations.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations against an :class:`AsyncEngine`."""
    section = config.get_section(config.config_ini_section, {})
    connectable: AsyncEngine = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )
    install_sqlite_pragmas(connectable)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Drive ``run_async_migrations`` from sync Alembic context."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
