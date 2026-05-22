"""ROUGE-1 / ROUGE-2 / ROUGE-L F1 (rouge-score, lazy-imported).

The primary ``value`` is the F1 of the configured variant
(``MetricSpec.config['variant']``, default ``"rougeL"``); every
variant's P/R/F is reported as :class:`SubScore` so the dashboard can
render the full set.
"""

from __future__ import annotations

from typing import Any

from backend.contracts.metric_result import MetricInputs, SubScore
from backend.metrics.base import BaseMetric, metric_factory
from backend.metrics.registry import register_metric

_DEFAULT_VARIANTS: tuple[str, ...] = ("rouge1", "rouge2", "rougeL")


class RougeMetric(BaseMetric):
    """ROUGE-1/2/L family using ``rouge-score``."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Defer the rouge-score import to first compute."""
        super().__init__(*args, **kwargs)
        self._scorer: Any = None
        self._variants: tuple[str, ...] = _DEFAULT_VARIANTS

    def _ensure_scorer(self) -> Any:
        """
        Import and cache dependencies required by the metric.

        :return: A :class:`Any` instance.
        """
        if self._scorer is None:
            from rouge_score.rouge_scorer import (  # type: ignore[import-untyped]
                RougeScorer,
            )

            variants_csv = self.spec.config.get("variants", ",".join(_DEFAULT_VARIANTS))
            self._variants = tuple(v.strip() for v in variants_csv.split(",") if v.strip())
            self._scorer = RougeScorer(list(self._variants), use_stemmer=True)
        return self._scorer

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
            raise ValueError("rouge requires `reference`")
        scorer = self._ensure_scorer()
        scores = scorer.score(inputs.reference, inputs.candidate)
        primary_variant = self.spec.config.get("variant", "rougeL")
        if primary_variant not in scores:
            primary_variant = next(iter(scores))
        primary = float(scores[primary_variant].fmeasure)
        sub_values: list[SubScore] = []
        for variant, sc in scores.items():
            sub_values.append(SubScore(name=f"{variant}_p", value=float(sc.precision)))
            sub_values.append(SubScore(name=f"{variant}_r", value=float(sc.recall)))
            sub_values.append(SubScore(name=f"{variant}_f", value=float(sc.fmeasure)))
        return primary, sub_values


try:
    register_metric("rouge", metric_factory(RougeMetric))
except ValueError:
    pass
