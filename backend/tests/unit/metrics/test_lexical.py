"""Lexical-metric behavioral tests."""

from __future__ import annotations

from aef.contracts.metric_result import (
    MetricInputs,
    MetricKind,
    MetricResult,
    MetricSpec,
    MetricStatus,
)
from aef.metrics import build_metric


def _inputs(candidate: str, reference: str | None) -> MetricInputs:
    return MetricInputs(
        sample_idx=0,
        input="What is 1+1?",
        candidate=candidate,
        reference=reference,
    )


async def test_exact_match_hit() -> None:
    metric = build_metric(MetricSpec(name="exact_match", kind=MetricKind.LEXICAL))
    result = await metric.compute(_inputs("hello", "Hello!"))
    assert result.status == MetricStatus.OK
    assert result.value == 1.0


async def test_exact_match_miss() -> None:
    metric = build_metric(MetricSpec(name="exact_match", kind=MetricKind.LEXICAL))
    result = await metric.compute(_inputs("hi", "hello"))
    assert result.value == 0.0


async def test_exact_match_no_reference_errors() -> None:
    metric = build_metric(MetricSpec(name="exact_match", kind=MetricKind.LEXICAL))
    result = await metric.compute(_inputs("hi", None))
    assert result.status == MetricStatus.ERROR


async def test_token_f1_full_overlap() -> None:
    metric = build_metric(MetricSpec(name="token_f1", kind=MetricKind.LEXICAL))
    result = await metric.compute(_inputs("the quick brown fox", "The quick brown FOX"))
    assert result.value == 1.0


async def test_token_f1_partial_overlap() -> None:
    metric = build_metric(MetricSpec(name="token_f1", kind=MetricKind.LEXICAL))
    result = await metric.compute(
        _inputs("the quick brown fox", "the lazy brown dog"),
    )
    assert result.value is not None
    assert 0.0 < result.value < 1.0


async def test_ngram_overlap_with_n_3() -> None:
    metric = build_metric(
        MetricSpec(name="ngram_overlap", kind=MetricKind.LEXICAL, config={"n": "3"}),
    )
    result = await metric.compute(_inputs("the quick brown fox", "the quick brown fox"))
    assert result.value == 1.0


async def test_bleu_smoke() -> None:
    metric = build_metric(MetricSpec(name="bleu", kind=MetricKind.LEXICAL))
    result = await metric.compute(
        _inputs("the cat sat on the mat", "the cat sat on the mat"),
    )
    assert result.status == MetricStatus.OK
    assert result.value is not None
    assert result.value > 0.5


async def test_chrf_smoke() -> None:
    metric = build_metric(MetricSpec(name="chrf", kind=MetricKind.LEXICAL))
    result = await metric.compute(_inputs("hello world", "hello world"))
    assert result.status == MetricStatus.OK
    assert result.value is not None
    assert result.value > 0.9


async def test_rouge_smoke() -> None:
    metric = build_metric(MetricSpec(name="rouge", kind=MetricKind.LEXICAL))
    result = await metric.compute(
        _inputs("the cat sat on the mat", "the cat sat on the mat"),
    )
    assert result.status == MetricStatus.OK
    assert result.value is not None
    assert result.value > 0.9
    sub_names = {sv.name for sv in result.sub_values}
    assert "rougeL_f" in sub_names or "rouge1_f" in sub_names


async def test_fuzzy_match_smoke() -> None:
    metric = build_metric(MetricSpec(name="fuzzy_match", kind=MetricKind.LEXICAL))
    result = await metric.compute(_inputs("hello world", "hello world!"))
    assert result.value is not None
    assert result.value > 0.9


async def test_aggregate_handles_empty_input() -> None:
    metric = build_metric(MetricSpec(name="exact_match", kind=MetricKind.LEXICAL))
    result = await metric.aggregate([])
    assert result.status == MetricStatus.SKIPPED


async def test_aggregate_computes_mean() -> None:
    metric = build_metric(MetricSpec(name="exact_match", kind=MetricKind.LEXICAL))
    per_sample: list[MetricResult] = []
    for i, (cand, ref) in enumerate(
        [("a", "a"), ("a", "b"), ("c", "c"), ("d", "d")],
    ):
        per_sample.append(
            await metric.compute(
                MetricInputs(sample_idx=i, input="x", candidate=cand, reference=ref),
            ),
        )
    aggregate = await metric.aggregate(per_sample)
    assert aggregate.status == MetricStatus.OK
    assert aggregate.value == 0.75
