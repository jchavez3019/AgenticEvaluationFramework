"""Strict equality after configurable normalization (per ADR-0004 §4)."""

from __future__ import annotations

from aef.contracts.metric_result import MetricInputs, SubScore
from aef.metrics.base import BaseMetric, metric_factory
from aef.metrics.lexical._text import normalize
from aef.metrics.registry import register_metric


class ExactMatchMetric(BaseMetric):
    """Returns 1.0 when ``candidate == reference`` (after normalization)."""

    def _score(
        self,
        inputs: MetricInputs,
    ) -> tuple[float | None, list[SubScore]]:
        if inputs.reference is None:
            raise ValueError("exact_match requires `reference`")
        candidate = normalize(inputs.candidate)
        reference = normalize(inputs.reference)
        return (1.0 if candidate == reference else 0.0, [])


try:
    register_metric("exact_match", metric_factory(ExactMatchMetric))
except ValueError:
    pass
