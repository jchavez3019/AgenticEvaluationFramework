"""Latency operational metric (per ADR-0004 §4)."""

from __future__ import annotations

import statistics

from aef.contracts.metric_result import (
    MetricInputs,
    MetricResult,
    MetricStatus,
    SubScore,
)
from aef.metrics.base import BaseMetric, metric_factory
from aef.metrics.registry import register_metric


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    rank = pct * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = rank - lower
    return sorted_values[lower] + fraction * (sorted_values[upper] - sorted_values[lower])


class LatencyMetric(BaseMetric):
    """Reports per-sample generation latency; aggregate adds p50/p95/p99."""

    def _score(
        self,
        inputs: MetricInputs,
    ) -> tuple[float | None, list[SubScore]]:
        if inputs.generation is None:
            raise ValueError("latency metric requires generation metadata")
        return float(inputs.generation.latency_ms), []

    async def aggregate(
        self,
        per_sample: list[MetricResult],
    ) -> MetricResult:
        """Mean latency + p50/p95/p99 sub-scores."""
        scalars = [
            r.value for r in per_sample if r.status == MetricStatus.OK and r.value is not None
        ]
        if not scalars:
            return MetricResult(
                metric_name=self.spec.name,
                metric_version=self.spec.version,
                sample_idx=None,
                status=MetricStatus.SKIPPED,
                value=None,
                sub_values=[],
                compute_latency_ms=0.0,
            )
        return MetricResult(
            metric_name=self.spec.name,
            metric_version=self.spec.version,
            sample_idx=None,
            status=MetricStatus.OK,
            value=statistics.fmean(scalars),
            sub_values=[
                SubScore(name="p50", value=_percentile(scalars, 0.50)),
                SubScore(name="p95", value=_percentile(scalars, 0.95)),
                SubScore(name="p99", value=_percentile(scalars, 0.99)),
                SubScore(name="min", value=min(scalars)),
                SubScore(name="max", value=max(scalars)),
                SubScore(name="count", value=float(len(scalars))),
            ],
            compute_latency_ms=0.0,
        )


try:
    register_metric("latency", metric_factory(LatencyMetric))
except ValueError:
    pass
