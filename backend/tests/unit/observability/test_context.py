"""Tests for :mod:`backend.observability.context`."""

from __future__ import annotations

import asyncio

from backend.observability.context import current_context, run_context


def test_current_context_is_empty_outside_run_context() -> None:
    """Verify current context is empty outside run context."""
    ctx = current_context()
    assert ctx.run_id is None
    assert ctx.sample_idx is None
    assert ctx.stage is None


def test_run_context_sets_and_restores_values() -> None:
    """Verify run context sets and restores values."""

    async def _inner() -> None:
        """
        Inner.

        :return: The None result.
        """
        async with run_context(run_id="run-A", stage="setup"):
            ctx = current_context()
            assert ctx.run_id == "run-A"
            assert ctx.stage == "setup"
        # On exit, the values must be restored to the previous frame.
        ctx_after = current_context()
        assert ctx_after.run_id is None

    asyncio.run(_inner())


def test_nested_run_context_inherits_then_restores() -> None:
    """Verify nested run context inherits then restores."""

    async def _inner() -> None:
        """
        Inner.

        :return: The None result.
        """
        async with run_context(run_id="run-A", stage="setup"):
            async with run_context(stage="generation", sample_idx=5):
                ctx = current_context()
                assert ctx.run_id == "run-A"
                assert ctx.stage == "generation"
                assert ctx.sample_idx == 5
            after_inner = current_context()
            assert after_inner.stage == "setup"
            assert after_inner.sample_idx is None

    asyncio.run(_inner())
