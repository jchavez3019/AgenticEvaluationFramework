"""Strict equality after configurable normalization (per ADR-0004 §4)."""

from __future__ import annotations

from backend.contracts.metric_result import MetricInputs, SubScore
from backend.metrics.base import BaseMetric, metric_factory
from backend.metrics.lexical._text import normalize
from backend.metrics.registry import register_metric


class ExactMatchMetric(BaseMetric):
    """Returns 1.0 when ``candidate == reference`` (after normalization)."""

    def _score(
        self,
        inputs: MetricInputs,
    ) -> tuple[float | None, list[SubScore]]:
        """
        Compute the metric value for one sample.

        :param inputs: Per-sample metric inputs.

        :return: A :class:`tuple[float | None, list[SubScore]]` instance.
        """
        if inputs.reference is None:
            raise ValueError("exact_match requires `reference`")
        candidate = normalize(inputs.candidate)
        reference = normalize(inputs.reference)
        return (1.0 if candidate == reference else 0.0, [])


try:
    register_metric("exact_match", metric_factory(ExactMatchMetric))
except ValueError:
    pass
