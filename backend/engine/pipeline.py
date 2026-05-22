"""Shared pipeline helpers used by both engines.

The walking-skeleton ships only :class:`LocalEngine` so this module is
deliberately small — it contains the per-sample function the local
engine uses, plus the metric-applicability check that both engines
will share once :class:`DistributedEngine` lands.

# ADR: Execution Engine — Local and Distributed
# See: adr/0005-execution-engine-local-and-distributed.md
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from backend.contracts.metric_result import (
    MetricInputs,
    MetricResult,
    MetricStatus,
)
from backend.contracts.primitives import (
    ChatMessage,
    GenerationRequest,
    GenerationResponse,
)

if TYPE_CHECKING:
    from backend.adapters.models.base import ModelAdapter
    from backend.contracts.metric_result import MetricSpec
    from backend.contracts.primitives import EvaluationSample
    from backend.metrics.base import Metric


def _is_applicable(
    spec: MetricSpec,
    sample: EvaluationSample,
) -> bool:
    """
    Decide whether ``spec`` should run on ``sample``.

    Currently checks the four flags on :class:`MetricApplicability`. Statically-incompatible
    metrics are expected to be filtered before the engine starts; this function only handles
    the per-sample case.

    :param spec: :class:`MetricSpec` whose applicability flags are evaluated.
    :param sample: Evaluation sample being processed.

    :return: ``True`` when the metric should run on this sample.
    """
    rule = spec.applicable_when
    if rule.requires_reference and sample.reference is None:
        return False
    if rule.requires_references and not (sample.references or sample.reference):
        return False
    if rule.requires_context and not sample.context:
        return False
    if rule.requires_gold_context and not sample.gold_context:
        return False
    return True


async def generate_for_sample(
    *,
    sample: EvaluationSample,
    model: ModelAdapter,
    sampling: GenerationRequest | None = None,
) -> GenerationResponse:
    """
    Drive the model adapter for one sample, propagating latency.

    :param sample: Evaluation sample being processed.
    :param model: Model adapter used for generation.
    :param sampling: Generation sampling configuration.

    :return: :class:`GenerationResponse` instance.
    """
    request = sampling or GenerationRequest(
        messages=[ChatMessage(role="user", content=sample.input)],
    )
    request = GenerationRequest(
        messages=[ChatMessage(role="user", content=sample.input)],
        sampling=request.sampling,
    )
    start = time.perf_counter()
    response = await model.generate(request)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    if response.latency_ms == 0.0:
        response = response.model_copy(update={"latency_ms": elapsed_ms})
    return response


async def score_for_sample(
    *,
    sample: EvaluationSample,
    response: GenerationResponse,
    metrics: list[Metric],
) -> list[MetricResult]:
    """
    Run every applicable metric over ``sample`` / ``response``.

    :param sample: Evaluation sample being processed.
    :param response: Model generation response.
    :param metrics: Metric instances to apply.

    :return: One :class:`MetricResult` per registered metric (including skips).
    """
    results: list[MetricResult] = []
    for metric in metrics:
        if not _is_applicable(metric.spec, sample):
            results.append(
                MetricResult(
                    metric_name=metric.spec.name,
                    metric_version=metric.spec.version,
                    sample_idx=sample.idx,
                    status=MetricStatus.SKIPPED,
                    value=None,
                    sub_values=[],
                    compute_latency_ms=0.0,
                ),
            )
            continue
        inputs = MetricInputs(
            sample_idx=sample.idx,
            input=sample.input,
            candidate=response.text,
            reference=sample.reference,
            references=sample.references,
            context=sample.context,
            gold_context=sample.gold_context,
            sample_metadata=sample.metadata,
            generation=response,
        )
        result = await metric.compute(inputs)
        results.append(result)
    return results
