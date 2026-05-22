"""Per-sample cost (USD) operational metric — null when adapter doesn't report."""

from __future__ import annotations

from backend.contracts.metric_result import MetricInputs, SubScore
from backend.metrics.base import BaseMetric, metric_factory
from backend.metrics.registry import register_metric


class CostMetric(BaseMetric):
    """Reports the adapter's :attr:`Usage.cost_usd` if set; ``None`` otherwise."""

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
            raise ValueError("cost metric requires generation metadata")
        cost_usd = inputs.generation.usage.cost_usd
        if cost_usd is None:
            return None, []
        return float(cost_usd), []


try:
    register_metric("cost", metric_factory(CostMetric))
except ValueError:
    pass
