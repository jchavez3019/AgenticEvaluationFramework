"""Verify the Alembic migration produces the expected schema."""

from __future__ import annotations

import os
import shutil
import subprocess  # — Alembic CLI invocation in a controlled test.
from pathlib import Path

import pytest

from aef.persistence import SQLiteStorage


@pytest.mark.asyncio
async def test_alembic_upgrade_head_against_temp_sqlite(tmp_path: Path) -> None:
    """``alembic upgrade head`` must succeed against a fresh SQLite file."""
    db_path = tmp_path / "alembic-test.sqlite3"
    backend_root = Path(__file__).resolve().parents[3]

    env = os.environ.copy()
    env["AEF_DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

    uv_path = shutil.which("uv")
    assert uv_path is not None, "uv must be on PATH for the migration test"
    result = subprocess.run(  # noqa: S603 — args are a fixed allowlist.
        [uv_path, "run", "alembic", "upgrade", "head"],
        cwd=backend_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (
        result.returncode == 0
    ), f"alembic upgrade failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert db_path.exists()

    # Make sure the migrated schema is usable through the storage adapter.
    storage = SQLiteStorage.from_url(f"sqlite+aiosqlite:///{db_path}")
    try:
        runs_page = await storage.list_runs(
            query=__import__(
                "aef.contracts.persistence",
                fromlist=["RunQuery"],
            ).RunQuery()
        )
        assert runs_page.total == 0
    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_pragmas_are_applied_on_sqlite_connect(tmp_path: Path) -> None:
    """WAL + FK + ``synchronous=NORMAL`` must be active on every SQLite conn."""
    db_path = tmp_path / "pragma-test.sqlite3"
    storage = SQLiteStorage.from_url(f"sqlite+aiosqlite:///{db_path}")
    try:
        await storage.create_all()
        async with storage.engine.connect() as conn:
            journal_mode = (await conn.exec_driver_sql("PRAGMA journal_mode;")).scalar_one()
            assert str(journal_mode).lower() == "wal"
            foreign_keys = (await conn.exec_driver_sql("PRAGMA foreign_keys;")).scalar_one()
            assert foreign_keys == 1
            synchronous = (await conn.exec_driver_sql("PRAGMA synchronous;")).scalar_one()
            # synchronous=NORMAL maps to integer 1 in SQLite's pragma readback.
            assert synchronous == 1
    finally:
        await storage.close()
