"""Metric registry behavior tests."""

from __future__ import annotations

import pytest

from backend.contracts.metric_result import MetricKind, MetricSpec
from backend.metrics import (
    Metric,
    build_metric,
    list_metrics,
    register_metric,
    unregister_metric,
)
from backend.metrics.base import BaseMetric, metric_factory


def test_default_suite_registered() -> None:
    """Verify default suite registered."""
    expected = {
        "exact_match",
        "token_f1",
        "ngram_overlap",
        "bleu",
        "rouge",
        "chrf",
        "meteor",
        "fuzzy_match",
        "latency",
        "token_counts",
        "cost",
        "output_validity",
    }
    registered = set(list_metrics())
    missing = expected - registered
    assert not missing, f"missing default metrics: {missing}"


def test_build_unknown_raises() -> None:
    """Verify build unknown raises."""
    with pytest.raises(KeyError, match="unknown metric"):
        build_metric(MetricSpec(name="not-a-real-metric", kind=MetricKind.LEXICAL))


def test_register_duplicate_raises() -> None:
    """Verify register duplicate raises."""
    from backend.contracts.metric_result import MetricInputs, SubScore

    class _Tmp(BaseMetric):
        """Minimal metric used to exercise duplicate registration errors."""

        def _score(
            self,
            inputs: MetricInputs,
        ) -> tuple[float | None, list[SubScore]]:
            """
            Compute the metric value for one sample.

            :param inputs: Per-sample metric inputs.

            :return: A :class:`tuple[float | None, list[SubScore]]` instance.
            """
            return 0.0, []

    register_metric("dup-test-metric", metric_factory(_Tmp))
    try:
        with pytest.raises(ValueError, match="already registered"):
            register_metric("dup-test-metric", metric_factory(_Tmp))
    finally:
        unregister_metric("dup-test-metric")


def test_built_metric_satisfies_protocol() -> None:
    """Verify built metric satisfies protocol."""
    metric = build_metric(
        MetricSpec(name="exact_match", kind=MetricKind.LEXICAL),
    )
    assert isinstance(metric, Metric)
