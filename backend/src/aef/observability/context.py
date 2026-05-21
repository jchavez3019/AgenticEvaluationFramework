"""Run-scoped context propagation via :mod:`contextvars`.

Every log record produced during an evaluation run carries ``run_id``,
``sample_idx``, and ``stage``. The engine sets these once at the top of
:meth:`ExecutionEngine.run` (and toggles ``stage`` between generation /
scoring); adapters and metrics never thread these values through their
signatures.

# ADR: Logging and Telemetry Contract
# See: adr/0012-logging-and-telemetry-contract.md
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from aef.contracts.primitives import PipelineStage


_RUN_ID: ContextVar[str | None] = ContextVar("aef.run_id", default=None)
_SAMPLE_IDX: ContextVar[int | None] = ContextVar("aef.sample_idx", default=None)
_STAGE: ContextVar[PipelineStage | None] = ContextVar("aef.stage", default=None)


@dataclass(frozen=True, slots=True)
class RunContext:
    """Snapshot of the current contextvars relevant to a run."""

    run_id: str | None
    sample_idx: int | None
    stage: PipelineStage | None


def current_context() -> RunContext:
    """Return the contextvars currently in scope.

    Adapters, metrics, and timing primitives read this snapshot to attach
    run / sample / stage metadata to log records and
    :class:`TimingRecord` entries.

    :returns: a frozen :class:`RunContext` snapshot. Any field is
        ``None`` when not set in the current task.
    """
    return RunContext(
        run_id=_RUN_ID.get(),
        sample_idx=_SAMPLE_IDX.get(),
        stage=_STAGE.get(),
    )


@asynccontextmanager
async def run_context(
    *,
    run_id: str | None = None,
    sample_idx: int | None = None,
    stage: PipelineStage | None = None,
) -> AsyncGenerator[RunContext]:
    """Enter a run-scoped context.

    Sets the contextvars referenced by :class:`ContextvarsFilter` and the
    timing primitives, yielding a :class:`RunContext` snapshot for
    callers that need it. On exit, every contextvar is restored to its
    previous value (the previous frame's), so nested ``run_context``
    calls compose cleanly.

    Only the keyword arguments that are not ``None`` overwrite the
    inherited context — passing ``stage="scoring"`` alone preserves the
    surrounding ``run_id`` / ``sample_idx``.

    :param run_id: optional new run id.
    :param sample_idx: optional new sample index.
    :param stage: optional new pipeline stage.
    :yields: a frozen :class:`RunContext` snapshot for the duration of
        the block.
    """
    tokens: list[Token[str | None] | Token[int | None] | Token[PipelineStage | None]] = []
    if run_id is not None:
        tokens.append(_RUN_ID.set(run_id))
    if sample_idx is not None:
        tokens.append(_SAMPLE_IDX.set(sample_idx))
    if stage is not None:
        tokens.append(_STAGE.set(stage))
    try:
        yield current_context()
    finally:
        for token in reversed(tokens):
            # Each contextvar exposes a Token typed against its own
            # value type; reset() correctly handles the union.
            token.var.reset(token)  # type: ignore[arg-type]


class ContextvarsFilter(logging.Filter):
    """Inject :func:`current_context` snapshot into every log record.

    Adds three attributes the JSON / console formatters know how to
    render: ``run_id``, ``sample_idx``, ``stage``. Records produced
    outside a :func:`run_context` block carry ``None`` for each.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Mutate ``record`` in-place to carry the run context."""
        ctx = current_context()
        record.run_id = ctx.run_id
        record.sample_idx = ctx.sample_idx
        record.stage = ctx.stage
        return True
