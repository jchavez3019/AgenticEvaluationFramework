"""Sentence-level BLEU using sacrebleu (lazy-imported).

We compute sentence BLEU per sample so the metric layer's per-sample /
aggregate split has clean semantics — :meth:`aggregate` reports the
mean which is a reasonable run-level rollup. The corpus-BLEU
distinction is a sacrebleu nuance handled internally.

# ADR: Default Metric Suite and Plugin Contract
# See: adr/0004-default-metric-suite-and-plugin-contract.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from backend.contracts.metric_result import MetricInputs, SubScore
from backend.metrics.base import BaseMetric, metric_factory
from backend.metrics.registry import register_metric

if TYPE_CHECKING:
    pass


class BleuMetric(BaseMetric):
    """Sentence BLEU (sacrebleu).

    Lazy-imports sacrebleu on first :meth:`compute` so ``import
    backend.metrics`` does not pull the dependency.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Defer the sacrebleu import to first compute."""
        super().__init__(*args, **kwargs)
        self._bleu_obj: Any = None

    def _ensure_bleu(self) -> Any:
        """
        Import and cache dependencies required by the metric.

        :return: A :class:`Any` instance.
        """
        if self._bleu_obj is None:
            import sacrebleu

            self._bleu_obj = sacrebleu
        return self._bleu_obj

    def _score(
        self,
        inputs: MetricInputs,
    ) -> tuple[float | None, list[SubScore]]:
        """
        Compute the metric value for one sample.

        :param inputs: Per-sample metric inputs.

        :return: A :class:`tuple[float | None, list[SubScore]]` instance.
        """
        references = inputs.references or ([inputs.reference] if inputs.reference else None)
        if not references:
            raise ValueError("bleu requires `reference` or `references`")
        sacrebleu = self._ensure_bleu()
        score = sacrebleu.sentence_bleu(inputs.candidate, references)
        # ``score.score`` is the BLEU score (0..100); we normalize to 0..1.
        return float(score.score) / 100.0, [
            SubScore(name="bleu_pct", value=float(score.score)),
        ]


try:
    register_metric("bleu", metric_factory(BleuMetric))
except ValueError:
    pass
