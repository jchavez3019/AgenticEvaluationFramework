"""Token-count operational metric (per ADR-0004 §4)."""

from __future__ import annotations

from backend.contracts.metric_result import MetricInputs, SubScore
from backend.metrics.base import BaseMetric, metric_factory
from backend.metrics.registry import register_metric


class TokenCountsMetric(BaseMetric):
    """Total token count as the primary value; sub-scores for prompt/completion."""

    def _score(
        self,
        inputs: MetricInputs,
    ) -> tuple[float | None, list[SubScore]]:
        """
        Compute the metric value for one sample.

        :param inputs: Per-sample metric inputs.

        :return: A :class:`tuple[float | None, list[SubScore]]` instance.
        """
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
