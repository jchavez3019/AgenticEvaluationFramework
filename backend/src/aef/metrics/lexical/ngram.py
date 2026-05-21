"""Configurable n-gram precision/recall/F1 (in-tree, no upstream library).

The metric reports F1 as the primary value with precision/recall as
sub-scores so the dashboard can render either. ``MetricSpec.config`` may
set the ``n`` parameter (default ``"4"``).

# ADR: Default Metric Suite and Plugin Contract
# See: adr/0004-default-metric-suite-and-plugin-contract.md
"""

from __future__ import annotations

from collections import Counter

from aef.contracts.metric_result import MetricInputs, SubScore
from aef.metrics.base import BaseMetric, metric_factory
from aef.metrics.lexical._text import normalize, whitespace_tokenize
from aef.metrics.registry import register_metric


def _ngrams(tokens: list[str], n: int) -> Counter[tuple[str, ...]]:
    if n <= 0 or len(tokens) < n:
        return Counter()
    return Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))


class NGramOverlapMetric(BaseMetric):
    """Modified n-gram overlap. ``MetricSpec.config['n']`` defaults to ``"4"``."""

    def _score(
        self,
        inputs: MetricInputs,
    ) -> tuple[float | None, list[SubScore]]:
        if inputs.reference is None:
            raise ValueError("ngram_overlap requires `reference`")
        n_str = self.spec.config.get("n", "4")
        try:
            n = int(n_str)
        except ValueError as exc:
            raise ValueError(f"ngram_overlap.n must be int, got {n_str!r}") from exc
        if n <= 0:
            raise ValueError(f"ngram_overlap.n must be >= 1, got {n}")

        cand = whitespace_tokenize(normalize(inputs.candidate))
        ref = whitespace_tokenize(normalize(inputs.reference))
        cand_ngrams = _ngrams(cand, n)
        ref_ngrams = _ngrams(ref, n)
        cand_total = sum(cand_ngrams.values())
        ref_total = sum(ref_ngrams.values())
        overlap = sum((cand_ngrams & ref_ngrams).values())
        if cand_total == 0 and ref_total == 0:
            return 1.0, [
                SubScore(name="precision", value=1.0),
                SubScore(name="recall", value=1.0),
                SubScore(name="n", value=float(n)),
            ]
        precision = overlap / cand_total if cand_total else 0.0
        recall = overlap / ref_total if ref_total else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if precision + recall > 0 else 0.0
        return f1, [
            SubScore(name="precision", value=precision),
            SubScore(name="recall", value=recall),
            SubScore(name="n", value=float(n)),
        ]


try:
    register_metric("ngram_overlap", metric_factory(NGramOverlapMetric))
except ValueError:
    pass
