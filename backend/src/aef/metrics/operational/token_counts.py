"""Token-count operational metric (per ADR-0004 §4)."""

from __future__ import annotations

from aef.contracts.metric_result import MetricInputs, SubScore
from aef.metrics.base import BaseMetric, metric_factory
from aef.metrics.registry import register_metric


class TokenCountsMetric(BaseMetric):
    """Total token count as the primary value; sub-scores for prompt/completion."""

    def _score(
        self,
        inputs: MetricInputs,
    ) -> tuple[float | None, list[SubScore]]:
        if inputs.generation is None:
            raise ValueError("token_counts metric requires generation metadata")
        usage = inputs.generation.usage
        sub_values: list[SubScore] = []
        if usage.prompt_tokens is not None:
            sub_values.append(
                SubScore(name="prompt_tokens", value=float(usage.prompt_tokens)),
            )
        if usage.completion_tokens is not None:
            sub_values.append(
                SubScore(
                    name="completion_tokens",
                    value=float(usage.completion_tokens),
                ),
            )
        if usage.total_tokens is None:
            return None, sub_values
        return float(usage.total_tokens), sub_values


try:
    register_metric("token_counts", metric_factory(TokenCountsMetric))
except ValueError:
    pass
