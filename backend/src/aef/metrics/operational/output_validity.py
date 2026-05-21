"""JSON parse-success rate operational metric (per ADR-0004 §4).

The metric returns 1.0 when ``candidate`` parses as JSON, 0.0 when it
does not. ``MetricSpec.config['mode']`` accepts ``"json"`` (the default
— attempts ``json.loads``) or ``"non_empty"`` (returns 1.0 when the
trimmed candidate is non-empty).
"""

from __future__ import annotations

import json

from aef.contracts.metric_result import MetricInputs, SubScore
from aef.metrics.base import BaseMetric, metric_factory
from aef.metrics.registry import register_metric


class OutputValidityMetric(BaseMetric):
    """Validate the candidate against a configured shape predicate."""

    def _score(
        self,
        inputs: MetricInputs,
    ) -> tuple[float | None, list[SubScore]]:
        mode = self.spec.config.get("mode", "json")
        if mode == "json":
            try:
                json.loads(inputs.candidate)
            except (ValueError, TypeError):
                return 0.0, [SubScore(name="mode", value=0.0, notes="json")]
            return 1.0, [SubScore(name="mode", value=1.0, notes="json")]
        if mode == "non_empty":
            return (1.0 if inputs.candidate.strip() else 0.0), [
                SubScore(name="mode", value=1.0, notes="non_empty"),
            ]
        raise ValueError(f"output_validity: unsupported mode {mode!r}")


try:
    register_metric("output_validity", metric_factory(OutputValidityMetric))
except ValueError:
    pass
