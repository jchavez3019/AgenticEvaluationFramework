"""Operational-metric tests."""

from __future__ import annotations

from aef.contracts.metric_result import (
    MetricInputs,
    MetricKind,
    MetricResult,
    MetricSpec,
    MetricStatus,
)
from aef.contracts.primitives import GenerationResponse, Usage
from aef.metrics import build_metric


def _inputs(*, candidate: str = "ok", generation: GenerationResponse | None = None) -> MetricInputs:
    return MetricInputs(
        sample_idx=0,
        input="x",
        candidate=candidate,
        reference="ok",
        generation=generation,
    )


async def test_latency_value_matches_generation() -> None:
    metric = build_metric(MetricSpec(name="latency", kind=MetricKind.OPERATIONAL))
    result = await metric.compute(
        _inputs(generation=GenerationResponse(text="ok", latency_ms=42.0)),
    )
    assert result.status == MetricStatus.OK
    assert result.value == 42.0


async def test_latency_aggregate_reports_percentiles() -> None:
    metric = build_metric(MetricSpec(name="latency", kind=MetricKind.OPERATIONAL))
    per_sample: list[MetricResult] = []
    for i, ms in enumerate([10.0, 20.0, 30.0, 40.0, 50.0]):
        per_sample.append(
            await metric.compute(
                MetricInputs(
                    sample_idx=i,
                    input="x",
                    candidate="ok",
                    generation=GenerationResponse(text="ok", latency_ms=ms),
                ),
            ),
        )
    aggregate = await metric.aggregate(per_sample)
    assert aggregate.status == MetricStatus.OK
    assert aggregate.value == 30.0
    sub_names = {sv.name for sv in aggregate.sub_values}
    assert {"p50", "p95", "p99", "min", "max", "count"}.issubset(sub_names)


async def test_token_counts_includes_subscores() -> None:
    metric = build_metric(MetricSpec(name="token_counts", kind=MetricKind.OPERATIONAL))
    result = await metric.compute(
        _inputs(
            generation=GenerationResponse(
                text="ok",
                usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            ),
        ),
    )
    assert result.value == 15.0
    sub_names = {sv.name for sv in result.sub_values}
    assert sub_names == {"prompt_tokens", "completion_tokens"}


async def test_token_counts_handles_unknown_total() -> None:
    metric = build_metric(MetricSpec(name="token_counts", kind=MetricKind.OPERATIONAL))
    result = await metric.compute(
        _inputs(generation=GenerationResponse(text="ok", usage=Usage())),
    )
    assert result.value is None


async def test_cost_returns_none_when_missing() -> None:
    metric = build_metric(MetricSpec(name="cost", kind=MetricKind.OPERATIONAL))
    result = await metric.compute(
        _inputs(generation=GenerationResponse(text="ok")),
    )
    assert result.value is None


async def test_cost_returns_value_when_set() -> None:
    metric = build_metric(MetricSpec(name="cost", kind=MetricKind.OPERATIONAL))
    result = await metric.compute(
        _inputs(generation=GenerationResponse(text="ok", usage=Usage(cost_usd=0.0125))),
    )
    assert result.value == 0.0125


async def test_output_validity_json_pass() -> None:
    metric = build_metric(
        MetricSpec(name="output_validity", kind=MetricKind.OPERATIONAL),
    )
    result = await metric.compute(_inputs(candidate='{"answer": 4}'))
    assert result.value == 1.0


async def test_output_validity_json_fail() -> None:
    metric = build_metric(
        MetricSpec(name="output_validity", kind=MetricKind.OPERATIONAL),
    )
    result = await metric.compute(_inputs(candidate="not json"))
    assert result.value == 0.0


async def test_output_validity_non_empty_mode() -> None:
    metric = build_metric(
        MetricSpec(
            name="output_validity",
            kind=MetricKind.OPERATIONAL,
            config={"mode": "non_empty"},
        ),
    )
    assert (await metric.compute(_inputs(candidate="hi"))).value == 1.0
    assert (await metric.compute(_inputs(candidate="   "))).value == 0.0
