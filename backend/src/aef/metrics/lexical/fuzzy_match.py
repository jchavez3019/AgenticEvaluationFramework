"""Fuzzy match via rapidfuzz (token-set ratio, lazy-imported)."""

from __future__ import annotations

from typing import Any

from aef.contracts.metric_result import MetricInputs, SubScore
from aef.metrics.base import BaseMetric, metric_factory
from aef.metrics.registry import register_metric


class FuzzyMatchMetric(BaseMetric):
    """token_set_ratio normalized to ``[0, 1]`` (rapidfuzz)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Hold the rapidfuzz module reference (lazy)."""
        super().__init__(*args, **kwargs)
        self._fuzz: Any = None

    def _score(
        self,
        inputs: MetricInputs,
    ) -> tuple[float | None, list[SubScore]]:
        if inputs.reference is None:
            raise ValueError("fuzzy_match requires `reference`")
        if self._fuzz is None:
            from rapidfuzz import fuzz

            self._fuzz = fuzz
        token_set = self._fuzz.token_set_ratio(inputs.candidate, inputs.reference) / 100.0
        ratio = self._fuzz.ratio(inputs.candidate, inputs.reference) / 100.0
        return float(token_set), [
            SubScore(name="ratio", value=float(ratio)),
        ]


try:
    register_metric("fuzzy_match", metric_factory(FuzzyMatchMetric))
except ValueError:
    pass
