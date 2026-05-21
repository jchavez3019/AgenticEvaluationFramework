"""Metric Protocol + thin in-tree base class for the shipped suite.

The :class:`Metric` Protocol is what third-party metrics implement. The
:class:`BaseMetric` class is an internal convenience for the in-tree
metrics: it knows how to time a compute, attach the metric name /
version onto the :class:`MetricResult`, and provide a default
``compute_batch`` that maps over ``compute``. Third parties are free to
implement the Protocol directly without inheriting from this class.

# ADR: Default Metric Suite and Plugin Contract
# See: adr/0004-default-metric-suite-and-plugin-contract.md
"""

from __future__ import annotations

import math
import statistics
import time
from abc import abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from aef.contracts.metric_result import (
    MetricInputs,
    MetricResult,
    MetricSpec,
    MetricStatus,
    SubScore,
)

if TYPE_CHECKING:
    pass


@runtime_checkable
class Metric(Protocol):
    """The contract every metric satisfies (per ADR-0004 §1)."""

    spec: MetricSpec

    async def compute(self, inputs: MetricInputs) -> MetricResult:
        """Score one sample."""
        ...

    async def compute_batch(
        self,
        inputs: list[MetricInputs],
    ) -> list[MetricResult]:
        """Score a batch of samples; default implementation maps :meth:`compute`."""
        ...

    async def aggregate(
        self,
        per_sample: list[MetricResult],
    ) -> MetricResult:
        """Compute a single run-level :class:`MetricResult`."""
        ...

    async def close(self) -> None:
        """Release any held resources (idempotent)."""
        ...


class BaseMetric:
    """Convenience base class for the in-tree v1 metrics.

    Third-party metrics typically implement :class:`Metric` directly;
    this class exists so the dozen metrics shipped by the framework
    don't repeat the same boilerplate (timing, status handling, mean
    aggregation).
    """

    def __init__(self, spec: MetricSpec) -> None:
        """Hold the spec for later compute calls."""
        self.spec = spec

    @abstractmethod
    def _score(self, inputs: MetricInputs) -> tuple[float | None, list[SubScore]]:
        """Compute the primary scalar + structured sub-scores for one sample."""

    async def compute(self, inputs: MetricInputs) -> MetricResult:
        """Score one sample, attaching latency + status + spec metadata."""
        start = time.perf_counter()
        try:
            value, sub_values = self._score(inputs)
        except Exception as exc:  # — converted into a MetricResult.
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            return MetricResult(
                metric_name=self.spec.name,
                metric_version=self.spec.version,
                sample_idx=inputs.sample_idx,
                status=MetricStatus.ERROR,
                value=None,
                sub_values=[],
                compute_latency_ms=elapsed_ms,
                exception_class=exc.__class__.__name__,
                exception_message=str(exc),
            )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return MetricResult(
            metric_name=self.spec.name,
            metric_version=self.spec.version,
            sample_idx=inputs.sample_idx,
            status=MetricStatus.OK,
            value=value,
            sub_values=sub_values,
            compute_latency_ms=elapsed_ms,
        )

    async def compute_batch(
        self,
        inputs: list[MetricInputs],
    ) -> list[MetricResult]:
        """Map :meth:`compute` over the batch (subclasses can override)."""
        return [await self.compute(item) for item in inputs]

    async def aggregate(
        self,
        per_sample: list[MetricResult],
    ) -> MetricResult:
        """Mean of every successful per-sample :attr:`MetricResult.value`.

        Skipped or errored samples are ignored. Run-level metrics that
        cannot be reduced to a mean (Self-BLEU, retrieval recall over
        a per-run set) override this method.
        """
        scalars = [
            r.value for r in per_sample if r.status == MetricStatus.OK and r.value is not None
        ]
        mean_value = statistics.fmean(scalars) if scalars else None
        sub_values: list[SubScore] = []
        if scalars:
            sub_values.append(SubScore(name="count", value=float(len(scalars))))
            if len(scalars) > 1:
                sub_values.append(
                    SubScore(name="stdev", value=statistics.stdev(scalars)),
                )
            sub_values.append(SubScore(name="min", value=min(scalars)))
            sub_values.append(SubScore(name="max", value=max(scalars)))
        if mean_value is not None and math.isnan(mean_value):
            mean_value = None
        return MetricResult(
            metric_name=self.spec.name,
            metric_version=self.spec.version,
            sample_idx=None,
            status=MetricStatus.OK if scalars else MetricStatus.SKIPPED,
            value=mean_value,
            sub_values=sub_values,
            compute_latency_ms=0.0,
        )

    async def close(self) -> None:
        """Release resources held by the metric (no-op for the in-tree suite)."""
        return None


def metric_factory(metric_cls: type[BaseMetric]) -> Callable[[MetricSpec], Metric]:
    """Return a registry-friendly factory for an in-tree metric class."""

    def _factory(spec: MetricSpec) -> Metric:
        return metric_cls(spec)

    return _factory
