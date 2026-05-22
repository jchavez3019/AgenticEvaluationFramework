"""Timing primitives — :func:`timed` plus the :class:`TelemetryRecorder`.

Use :func:`timed` as either a decorator or an async/sync context manager.
Every measured block emits a :class:`TimingRecord`, keyed by ``run_id``,
into a process-wide :class:`TelemetryRecorder`. At run finalize the
engine calls :meth:`TelemetryRecorder.dump_run` to materialize a
:class:`TelemetryReport`.

# ADR: Logging and Telemetry Contract
# See: adr/0012-logging-and-telemetry-contract.md
"""

from __future__ import annotations

import math
import statistics
import threading
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from datetime import UTC, datetime
from functools import wraps
from types import TracebackType
from typing import TYPE_CHECKING, ParamSpec, TypeVar, cast

from backend.contracts.telemetry import (
    StageSummary,
    TelemetryReport,
    ThroughputCounters,
    TimingRecord,
)
from backend.observability.context import current_context

if TYPE_CHECKING:
    from backend.contracts.primitives import PipelineStage


P = ParamSpec("P")
T = TypeVar("T")


class TelemetryRecorder:
    """Process-wide store of :class:`TimingRecord` keyed by ``run_id``.

    Records produced outside any :func:`run_context` block (i.e., when
    ``run_id`` is ``None``) are dropped — they cannot be assigned to a
    run. A future plan may add a "global" bucket if startup-time timings
    become interesting.
    """

    def __init__(self) -> None:
        """Initialize the recorder with an empty per-run buffer."""
        self._records: dict[str, list[TimingRecord]] = defaultdict(list)
        self._started: dict[str, datetime] = {}
        self._finished: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def record(self, run_id: str | None, record: TimingRecord) -> None:
        """
        Append ``record`` to the recorder for ``run_id``.

        :param run_id: the run id from :func:`current_context`. When ``None``, the record is
                       dropped silently.
        :param record: the entry to store.
        """
        if run_id is None:
            return
        with self._lock:
            self._records[run_id].append(record)
            now = datetime.now(UTC)
            self._started.setdefault(run_id, now)
            self._finished[run_id] = now

    def reset(self, run_id: str | None = None) -> None:
        """
        Drop recorded entries (entirely, or for a single run).

        Tests use this to keep recorder state from leaking between cases. Production code never
        calls it — runs finalize via :meth:`dump_run`.

        :param run_id: Unique run identifier.
        """
        with self._lock:
            if run_id is None:
                self._records.clear()
                self._started.clear()
                self._finished.clear()
            else:
                self._records.pop(run_id, None)
                self._started.pop(run_id, None)
                self._finished.pop(run_id, None)

    def dump_run(self, run_id: str) -> TelemetryReport:
        """
        Compute and return a :class:`TelemetryReport` for ``run_id``.

        Per-stage rollups (p50/p95/p99) are derived from :attr:`per_record`; the recorder does
        not pre-aggregate.

        :param run_id: identifies the run; must have at least one recorded entry.

        :return: a fully-populated :class:`TelemetryReport`. :raises KeyError: when no entries
                 were recorded for the run.
        """
        with self._lock:
            records = list(self._records.get(run_id, ()))
            started = self._started.get(run_id)
            finished = self._finished.get(run_id)

        if started is None or finished is None or not records:
            raise KeyError(f"No telemetry recorded for run {run_id!r}.")

        per_stage = _summarize_stages(records)
        counters = ThroughputCounters()
        total_ms = (finished - started).total_seconds() * 1000.0
        return TelemetryReport(
            run_id=run_id,
            started_at=started,
            finished_at=finished,
            total_duration_ms=total_ms,
            per_record=records,
            per_stage=per_stage,
            counters=counters,
        )


_RECORDER = TelemetryRecorder()


def get_recorder() -> TelemetryRecorder:
    """
    Return the process-wide :class:`TelemetryRecorder`.

    Tests inspect / reset this instance via the ``caplog_aef`` fixture family in
    :mod:`backend.tests.conftest`.


    :return: :class:`TelemetryRecorder` instance.
    """
    return _RECORDER


def _summarize_stages(records: list[TimingRecord]) -> list[StageSummary]:
    """
    Aggregate timing records into per-stage summaries.

    :param records: Collected timing records.

    :return: A :class:`list[StageSummary]` instance.
    """
    by_stage: dict[PipelineStage, list[TimingRecord]] = defaultdict(list)
    for r in records:
        by_stage[r.stage].append(r)
    summaries: list[StageSummary] = []
    for stage, items in by_stage.items():
        durations = [r.duration_ms for r in items]
        errors = sum(1 for r in items if r.exception_class is not None)
        summaries.append(
            StageSummary(
                stage=stage,
                total_ms=sum(durations),
                samples_processed=len(items),
                p50_ms=_percentile(durations, 0.50),
                p95_ms=_percentile(durations, 0.95),
                p99_ms=_percentile(durations, 0.99),
                error_count=errors,
            ),
        )
    return summaries


def _percentile(values: list[float], q: float) -> float:
    """
    Compute the ``q`` percentile of ``values``.

    :param values: Numeric samples.
    :param q: Quantile in ``[0, 1]``.

    :return: The float result.
    """
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    sorted_values = sorted(values)
    pos = q * (len(sorted_values) - 1)
    lower_idx = math.floor(pos)
    upper_idx = math.ceil(pos)
    if lower_idx == upper_idx:
        return sorted_values[lower_idx]
    fraction = pos - lower_idx
    return statistics.fmean(
        [sorted_values[lower_idx], sorted_values[upper_idx]],
        weights=[1 - fraction, fraction],
    )


class _Timed(AbstractContextManager[float], AbstractAsyncContextManager[float]):
    """The object returned by :func:`timed` — sync, async, and decorator usable.

    The same instance can be used as a sync ``with`` block, an
    ``async with`` block, or by calling it on a function — in which case
    a wrapped function is returned. Wrapping wraps both sync and async
    callables; the :class:`_Timed` instance is single-use as a context
    manager but freely reusable as a decorator factory.
    """

    __slots__ = ("_phase", "_start", "_recorder")

    def __init__(self, phase: str) -> None:
        """
        Configure the manager with a phase label.

        :param phase: Timing phase label recorded in telemetry.
        """
        self._phase = phase
        self._start: float = 0.0
        self._recorder = _RECORDER

    def __enter__(self) -> float:
        """Enter the synchronous context manager.

        :return: ``time.perf_counter()`` value at context entry.
        """
        self._start = time.perf_counter()
        return self._start

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """
        Exit the synchronous context manager.

        :param exc_type: Exception type raised in the block, if any.
        :param exc: Active exception instance, if any.
        :param tb: Traceback object for ``exc``, if any.
        """
        self._record(exc_type)

    async def __aenter__(self) -> float:
        """Enter the asynchronous context manager.

        :return: ``time.perf_counter()`` value at context entry.
        """
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """
        Exit the asynchronous context manager.

        :param exc_type: Exception type raised in the block, if any.
        :param exc: Active exception instance, if any.
        :param tb: Traceback object for ``exc``, if any.
        """
        self._record(exc_type)

    def __call__(self, fn: Callable[P, T]) -> Callable[P, T]:
        """
        Decorate ``fn`` so each call produces a :class:`TimingRecord`.

        :param fn: Callable to wrap with timing instrumentation.

        :return: Wrapped callable that records a :class:`TimingRecord` per invocation.
        """
        phase = self._phase
        if _is_coroutine_function(fn):
            afn = cast("Callable[P, Awaitable[T]]", fn)

            @wraps(afn)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                """
                Record timing around an asynchronous wrapped call.

                :return: Result of the wrapped coroutine.
                """
                async with _Timed(phase):
                    return await afn(*args, **kwargs)

            return cast("Callable[P, T]", async_wrapper)

        @wraps(fn)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            """
            Record timing around a synchronous wrapped call.

            :return: Result of the wrapped function.
            """
            with _Timed(phase):
                return fn(*args, **kwargs)

        return sync_wrapper

    def _record(self, exc_type: type[BaseException] | None) -> None:
        """
        Persist one timing record for the current context.

        :param exc_type: Exception type raised in the block, if any.
        """
        duration_ms = (time.perf_counter() - self._start) * 1000.0
        ctx = current_context()
        record = TimingRecord(
            phase=self._phase,
            duration_ms=duration_ms,
            sample_idx=ctx.sample_idx,
            stage=ctx.stage if ctx.stage is not None else "setup",
            exception_class=exc_type.__name__ if exc_type is not None else None,
        )
        self._recorder.record(ctx.run_id, record)


def timed(phase: str) -> _Timed:
    """
    Time a phase as a decorator or (async) context manager.

    Usage as a context manager::  with timed("metric.bleu"): ...  Usage as an async context
    manager::  async with timed("generation"): ...  Usage as a decorator (sync or async)::
    @timed("dataset.load") async def load() -> ...: ...  The recorded :class:`TimingRecord`
    automatically picks up the ``run_id`` / ``sample_idx`` / ``stage`` from the surrounding
    :func:`run_context`.

    :param phase: Human-readable phase label. Conventional values: ``generation``,
                  ``metric.<name>``, ``dataset.load``, ``persist``, ``judge.<name>``.

    :return: A :class:`_Timed` instance usable as a context manager or decorator.
    """
    return _Timed(phase)


def _is_coroutine_function(fn: object) -> bool:
    """
    Return whether ``fn`` is a coroutine function.

    :param fn: Callable to wrap or inspect.

    :return: The bool result.
    """
    import inspect

    return inspect.iscoroutinefunction(fn)
