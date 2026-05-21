"""Shared pytest configuration and fixtures.

Fixtures land here progressively as later milestones bring in mock
adapters (M3), in-memory SQLite (M4), the local engine, and CLI
scaffolding (M6). Each fixture is documented inline so the canonical
fixture names called out by the walking-skeleton plan stay discoverable.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from aef.observability import TelemetryRecorder, configure_logging
from aef.observability.timing import get_recorder
from aef.persistence import SQLiteStorage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator


@pytest.fixture(autouse=True)
def reset_aef_logger_handlers() -> Iterator[None]:
    """Detach handlers from the ``aef`` root logger between tests.

    :func:`configure_logging` mutates the root logger; without this
    fixture, handlers leak across tests and pytest's ``caplog`` (which
    attaches its own handler to the root) double-emits records.
    """
    yield
    root = logging.getLogger("aef")
    for handler in list(root.handlers):
        root.removeHandler(handler)


@pytest.fixture
def caplog_aef(
    caplog: pytest.LogCaptureFixture,
) -> Iterator[pytest.LogCaptureFixture]:
    """Pytest fixture that captures records from the ``aef`` logger tree.

    Tests assert structured fields (``run_id``, ``sample_idx``,
    ``stage``) attached by :class:`ContextvarsFilter` by inspecting
    ``caplog_aef.records``. ``configure_logging`` sets ``propagate=False``
    on the ``aef`` logger, so we attach pytest's capture handler
    directly to the ``aef`` logger for the duration of the test.
    """
    configure_logging()
    aef_logger = logging.getLogger("aef")
    aef_logger.addHandler(caplog.handler)
    caplog.set_level(logging.DEBUG, logger="aef")
    try:
        yield caplog
    finally:
        aef_logger.removeHandler(caplog.handler)


@pytest.fixture(autouse=True)
def reset_telemetry_recorder() -> Iterator[TelemetryRecorder]:
    """Drop any leftover :class:`TimingRecord` entries between tests."""
    recorder = get_recorder()
    recorder.reset()
    yield recorder
    recorder.reset()


@pytest.fixture
async def in_memory_storage() -> AsyncIterator[SQLiteStorage]:
    """Yield a fresh :class:`SQLiteStorage` backed by ``:memory:`` SQLite.

    The schema is created via ``Base.metadata.create_all`` rather than
    Alembic — Alembic's offline-vs-online machinery is exercised in a
    separate integration test. The fixture disposes of the engine on
    teardown so connection state never leaks between cases.
    """
    storage = SQLiteStorage.from_url("sqlite+aiosqlite:///:memory:")
    await storage.create_all()
    try:
        yield storage
    finally:
        await storage.close()
