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

    from backend.contracts.primitives import PipelineStage

# Thread-safe, asynchronous-aware global variables.
_RUN_ID: ContextVar[str | None] = ContextVar("backend.run_id", default=None)
_SAMPLE_IDX: ContextVar[int | None] = ContextVar("backend.sample_idx", default=None)
_STAGE: ContextVar[PipelineStage | None] = ContextVar("backend.stage", default=None)


@dataclass(frozen=True, slots=True)
class RunContext:
    """Snapshot of the current contextvars relevant to a run.

    * run_id: Active evaluation run identifier, or ``None`` outside a run.
    * sample_idx: Active sample index, or ``None`` when not processing a sample.
    * stage: Active pipeline stage, or ``None`` when no stage is set.
    """

    run_id: str | None
    sample_idx: int | None
    stage: PipelineStage | None


def current_context() -> RunContext:
    """
    Return the contextvars currently in scope.

    Adapters, metrics, and timing primitives read this snapshot to attach run / sample /
    stage metadata to log records and :class:`TimingRecord` entries.

    :return: a frozen :class:`RunContext` snapshot. Any field is ``None`` when not set in
             the current task.
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
    """
    Enter a run-scoped context.

    Sets the contextvars referenced by :class:`ContextvarsFilter` and the timing primitives,
    yielding a :class:`RunContext` snapshot for callers that need it. On exit, every
    contextvar is restored to its previous value (the previous frame's), so nested
    ``run_context`` calls compose cleanly.  Only the keyword arguments that are not ``None``
    overwrite the inherited context — passing ``stage="scoring"`` alone preserves the
    surrounding ``run_id`` / ``sample_idx``.

    :param run_id: optional new run id.
    :param sample_idx: optional new sample index.
    :param stage: optional new pipeline stage

    :yields: a frozen :class:`RunContext` snapshot for the duration of the block.

    :return: :class:`AsyncGenerator` instance.
    """
    tokens: list[Token[str | None] | Token[int | None] | Token[PipelineStage | None]] = []
    if run_id is not None:
        # ContextVar.set() updates _RUN_ID. The returned Token remembers the prior value.
        tokens.append(_RUN_ID.set(run_id))
    if sample_idx is not None:
        # Same pattern for _SAMPLE_IDX. Token stack enables nested run_context blocks.
        tokens.append(_SAMPLE_IDX.set(sample_idx))
    if stage is not None:
        # Same pattern for _STAGE.
        tokens.append(_STAGE.set(stage))
    try:
        # Yield a snapshot so callers can bind the block, e.g.:
        #   async with run_context(run_id=rid, stage="setup") as ctx:
        #       # ctx.run_id == rid, ctx.stage == "setup", ctx.sample_idx unchanged
        yield current_context()
    finally:
        # Pop tokens in reverse (LIFO) so each contextvar returns to its pre-block value.
        #
        # Nested example (_RUN_ID starts as None):
        # ```python
        # async with run_context(run_id="run_123"):
        #     # _RUN_ID.get() -> "run_123"; token remembers None
        #     async with run_context(run_id="run_456"):
        #         # _RUN_ID.get() -> "run_456"; token remembers "run_123"
        #     # inner exit: reset restores "run_123"
        #     # _RUN_ID.get() -> "run_123"
        # # outer exit: reset restores None
        # ```
        for token in reversed(tokens):
            # Token.var.reset() restores the ContextVar value from before .set() was invoked.
            token.var.reset(token)  # type: ignore[arg-type]


class ContextvarsFilter(logging.Filter):
    """Inject :func:`current_context` snapshot into every log record.

    Adds three attributes the JSON / console formatters know how to
    render: ``run_id``, ``sample_idx``, ``stage``. Records produced
    outside a :func:`run_context` block carry ``None`` for each.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Mutate ``record`` in-place to carry the run context.

        :param record: Log record to filter or format.

        :return: ``True`` when the predicate holds.
        """
        ctx = current_context()
        record.run_id = ctx.run_id
        record.sample_idx = ctx.sample_idx
        record.stage = ctx.stage
        return True
