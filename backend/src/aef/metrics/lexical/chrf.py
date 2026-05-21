"""chrF / chrF++ from sacrebleu (lazy-imported)."""

from __future__ import annotations

from typing import Any

from aef.contracts.metric_result import MetricInputs, SubScore
from aef.metrics.base import BaseMetric, metric_factory
from aef.metrics.registry import register_metric


class ChrfMetric(BaseMetric):
    """chrF++ score (sacrebleu)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Hold the sacrebleu module reference (lazy)."""
        super().__init__(*args, **kwargs)
        self._sacrebleu: Any = None

    def _score(
        self,
        inputs: MetricInputs,
    ) -> tuple[float | None, list[SubScore]]:
        references = inputs.references or ([inputs.reference] if inputs.reference else None)
        if not references:
            raise ValueError("chrf requires `reference` or `references`")
        if self._sacrebleu is None:
            import sacrebleu

            self._sacrebleu = sacrebleu
        score = self._sacrebleu.sentence_chrf(inputs.candidate, references)
        # sacrebleu returns chrF on a 0-100 scale; normalize.
        return float(score.score) / 100.0, [
            SubScore(name="chrf_pct", value=float(score.score)),
        ]


try:
    register_metric("chrf", metric_factory(ChrfMetric))
except ValueError:
    pass
