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

from backend.observability import ContextvarsFilter, TelemetryRecorder
from backend.observability.timing import get_recorder
from backend.persistence import SQLiteStorage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator


@pytest.fixture(autouse=True)
def reset_aef_logger_handlers() -> Iterator[None]:
    """
    Detach handlers from the ``backend`` root logger between tests.

    :func:`configure_logging` mutates the root logger; without this fixture, handlers leak
    across tests and pytest's ``caplog`` (which attaches its own handler to the root)
    double-emits records.


    :yields: Nothing; performs per-test logger handler cleanup.
    """
    yield
    root = logging.getLogger("backend")
    for handler in list(root.handlers):
        root.removeHandler(handler)


@pytest.fixture
def caplog_aef(
    caplog: pytest.LogCaptureFixture,
) -> Iterator[pytest.LogCaptureFixture]:
    """
    Pytest fixture that captures records from the ``backend`` logger tree.

    Attaches :class:`ContextvarsFilter` so log records carry ``run_id``,
    ``sample_idx``, and ``stage`` fields during tests.

    :param caplog: Pytest caplog fixture.

    :yields: The pytest log capture fixture bound to the ``backend`` logger.
    """
    aef_logger = logging.getLogger("backend")
    ctx_filter = ContextvarsFilter()
    caplog.handler.addFilter(ctx_filter)
    aef_logger.addHandler(caplog.handler)
    caplog.set_level(logging.DEBUG, logger="backend")
    try:
        yield caplog
    finally:
        aef_logger.removeHandler(caplog.handler)
        caplog.handler.removeFilter(ctx_filter)


@pytest.fixture(autouse=True)
def reset_telemetry_recorder() -> Iterator[TelemetryRecorder]:
    """
    Drop any leftover :class:`TimingRecord` entries between tests.

    :yields: The process-wide :class:`TelemetryRecorder` for the test body.
    """
    recorder = get_recorder()
    recorder.reset()
    yield recorder
    recorder.reset()


@pytest.fixture
async def in_memory_storage() -> AsyncIterator[SQLiteStorage]:
    """
    Yield a fresh :class:`SQLiteStorage` backed by ``:memory:`` SQLite.

    The schema is created via ``Base.metadata.create_all`` rather than Alembic — Alembic's
    offline-vs- online machinery is exercised in a separate integration test. The fixture
    disposes of the engine on teardown so connection state never leaks between cases.


    :yields: A connected in-memory :class:`SQLiteStorage` instance.
    """
    storage = SQLiteStorage.from_url("sqlite+aiosqlite:///:memory:")
    await storage.create_all()
    try:
        yield storage
    finally:
        await storage.close()
