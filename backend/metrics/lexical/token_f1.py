"""SQuAD-style token-level F1 (set-based) — see ADR-0004 §4."""

from __future__ import annotations

from collections import Counter

from backend.contracts.metric_result import MetricInputs, SubScore
from backend.metrics.base import BaseMetric, metric_factory
from backend.metrics.lexical._text import normalize, whitespace_tokenize
from backend.metrics.registry import register_metric


class TokenF1Metric(BaseMetric):
    """Token-overlap F1, multi-set (counts duplicate tokens)."""

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
            raise ValueError("token_f1 requires `reference`")
        cand_tokens = whitespace_tokenize(normalize(inputs.candidate))
        ref_tokens = whitespace_tokenize(normalize(inputs.reference))
        if not cand_tokens and not ref_tokens:
            return 1.0, []
        if not cand_tokens or not ref_tokens:
            return 0.0, []

        cand_counts = Counter(cand_tokens)
        ref_counts = Counter(ref_tokens)
        overlap = sum((cand_counts & ref_counts).values())
        if overlap == 0:
            return 0.0, [
                SubScore(name="precision", value=0.0),
                SubScore(name="recall", value=0.0),
            ]
        precision = overlap / sum(cand_counts.values())
        recall = overlap / sum(ref_counts.values())
        f1 = 2 * precision * recall / (precision + recall)
        return f1, [
            SubScore(name="precision", value=precision),
            SubScore(name="recall", value=recall),
        ]


try:
    register_metric("token_f1", metric_factory(TokenF1Metric))
except ValueError:
    pass
