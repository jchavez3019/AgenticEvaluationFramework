"""Tests for :mod:`backend.observability.timing` and the telemetry recorder."""

from __future__ import annotations

import asyncio

import pytest

from backend.observability import run_context, timed
from backend.observability.timing import get_recorder


def test_sync_context_manager_records_one_entry() -> None:
    """Verify sync context manager records one entry."""

    async def _inner() -> None:
        """
        Inner.

        :return: The None result.
        """
        async with run_context(run_id="run-1", stage="setup"):
            with timed("phase.sync"):
                pass

    asyncio.run(_inner())
    report = get_recorder().dump_run("run-1")
    assert len(report.per_record) == 1
    assert report.per_record[0].phase == "phase.sync"
    assert report.per_record[0].stage == "setup"


def test_async_context_manager_records_one_entry() -> None:
    """Verify async context manager records one entry."""

    async def _inner() -> None:
        """
        Inner.

        :return: The None result.
        """
        async with run_context(run_id="run-2", stage="generation"):
            async with timed("phase.async"):
                await asyncio.sleep(0)

    asyncio.run(_inner())
    report = get_recorder().dump_run("run-2")
    assert [r.phase for r in report.per_record] == ["phase.async"]
    assert report.per_record[0].stage == "generation"


def test_decorator_records_call_and_supports_async() -> None:
    """Verify the ``timed`` decorator records sync and async call timings."""

    @timed("phase.sync_fn")
    def square(x: int) -> int:
        """Square ``x`` under a ``timed`` decorator.

        :param x: Operand.
        :return: ``x ** 2``.
        """
        return x * x

    @timed("phase.async_fn")
    async def add_async(a: int, b: int) -> int:
        """Add two integers under an async ``timed`` decorator.

        :param a: First summand.
        :param b: Second summand.
        :return: ``a + b``.
        """
        await asyncio.sleep(0)
        return a + b

    async def _inner() -> tuple[int, int]:
        """Exercise decorated sync and async callables inside a run context.

        :return: ``(square(4), add_async(2, 3))`` results.
        """
        async with run_context(run_id="run-3", stage="scoring"):
            v1 = square(4)
            v2 = await add_async(2, 3)
            return v1, v2

    v1, v2 = asyncio.run(_inner())
    assert (v1, v2) == (16, 5)
    report = get_recorder().dump_run("run-3")
    phases = [r.phase for r in report.per_record]
    assert "phase.sync_fn" in phases
    assert "phase.async_fn" in phases


def test_recorder_drops_records_with_no_run_id() -> None:
    """Verify recorder drops records with no run id."""
    with timed("phase.orphan"):
        pass
    with pytest.raises(KeyError):
        get_recorder().dump_run("does-not-exist")


def test_exception_class_captured_when_block_raises() -> None:
    """Verify exception class captured when block raises."""

    async def _inner() -> None:
        """Raise inside ``timed`` and assert the exception class is recorded."""
        async with run_context(run_id="run-err", stage="scoring"):
            with pytest.raises(RuntimeError):
                with timed("phase.boom"):
                    raise RuntimeError("expected in test")

    asyncio.run(_inner())
    report = get_recorder().dump_run("run-err")
    assert report.per_record[0].exception_class == "RuntimeError"


def test_per_stage_summary_aggregates_durations() -> None:
    """Verify per stage summary aggregates durations."""

    async def _inner() -> None:
        """
        Inner.

        :return: The None result.
        """
        async with run_context(run_id="run-agg", stage="scoring"):
            for _ in range(3):
                with timed("phase.repeat"):
                    pass

    asyncio.run(_inner())
    report = get_recorder().dump_run("run-agg")
    assert any(s.stage == "scoring" and s.samples_processed == 3 for s in report.per_stage)


def test_dump_run_total_duration_matches_timestamps() -> None:
    """Verify dump run total duration matches timestamps."""

    async def _inner() -> None:
        """
        Inner.

        :return: The None result.
        """
        async with run_context(run_id="run-time", stage="setup"):
            with timed("phase.first"):
                pass

    asyncio.run(_inner())
    report = get_recorder().dump_run("run-time")
    elapsed = (report.finished_at - report.started_at).total_seconds() * 1000.0
    assert abs(report.total_duration_ms - elapsed) < 0.01
