"""Single-process asyncio :class:`LocalEngine`.

Implements the ADR-0005 §3 design at walking-skeleton fidelity: the
asyncio event loop drives the two-stage pipeline sequentially per
sample. Micro-batching, parallel pools, and queue-based pipeline
parallelism land in a follow-up milestone.

# ADR: Execution Engine — Local and Distributed
# See: adr/0005-execution-engine-local-and-distributed.md
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from backend.adapters.models.base import ModelAdapter
from backend.adapters.registry import build_dataset_adapter, build_model_adapter
from backend.contracts.metric_result import MetricResult
from backend.contracts.persistence import (
    MetricResultRecord,
    RunSummary,
    SampleRecord,
)
from backend.contracts.primitives import (
    ChatMessage,
    EngineConfig,
    EvaluationSample,
    GenerationRequest,
    GenerationResponse,
)
from backend.contracts.run import EvaluationRunResult
from backend.contracts.telemetry import TelemetryReport
from backend.engine.base import (
    ProgressEvent,
    ProgressSink,
    RunFinalized,
    SampleCompleted,
    SampleFailed,
    SampleStarted,
    StageCompleted,
    StageStarted,
)
from backend.engine.pipeline import generate_for_sample, score_for_sample
from backend.metrics.base import Metric
from backend.metrics.registry import build_metric
from backend.observability import get_logger, run_context, timed

if TYPE_CHECKING:
    from backend.contracts.run import EvaluationRunRequest
    from backend.persistence.base import StorageAdapter


logger = get_logger(__name__)


class LocalEngine:
    """Single-process :class:`ExecutionEngine` driven by asyncio."""

    def __init__(self, spec: EngineConfig | None = None) -> None:
        """Configure the engine; per-run settings still come from the request.

        :param spec: Optional default :class:`EngineConfig` when callers do not
            embed engine settings on each :class:`EvaluationRunRequest`.
        """
        self._explicit_spec = spec
        self._cancelled: set[str] = set()

    @property
    def spec(self) -> EngineConfig:
        """
        Resolve to the explicit spec when set, else a default ``EngineConfig``.

        :return: :class:`EngineConfig` instance.
        """
        return self._explicit_spec or EngineConfig()

    async def cancel(self, run_id: str) -> None:
        """
        Mark ``run_id`` as cancelled; in-flight samples wind down.

        :param run_id: Unique run identifier.
        """
        self._cancelled.add(run_id)

    async def close(self) -> None:
        """No-op for the local engine — there are no long-lived workers."""
        return None

    async def run(
        self,
        request: EvaluationRunRequest,
        storage: StorageAdapter,
        progress: ProgressSink | None = None,
    ) -> EvaluationRunResult:
        """
        Drive the run end-to-end and return the populated result.

        :param request: Evaluation run request payload.
        :param storage: Persistence adapter for run records.
        :param progress: Optional progress sink for streaming updates.

        :return: :class:`~backend.contracts.run.EvaluationRunResult`.
        """
        run_id = request.run_id
        started_at = datetime.now(UTC)
        run_started_perf = time.perf_counter()

        async with run_context(run_id=run_id, stage="setup"):
            await storage.create_run(request)
            await self._emit(
                progress,
                StageStarted(run_id=run_id, emitted_at=_now(), stage="setup"),
            )
            with timed("engine.setup"):
                model = build_model_adapter(request.model)
                metrics: list[Metric] = [build_metric(spec) for spec in request.metrics]
                dataset = build_dataset_adapter(request.dataset)
            await self._emit(
                progress,
                StageCompleted(
                    run_id=run_id,
                    emitted_at=_now(),
                    stage="setup",
                    duration_ms=_elapsed_ms(run_started_perf),
                ),
            )

        try:
            samples_pyd: list[EvaluationSample] = []
            generations: list[GenerationResponse] = []
            per_sample_results: list[MetricResult] = []
            error_count = 0

            async with run_context(run_id=run_id, stage="generation"):
                async with dataset:
                    samples_pyd = [row async for row in dataset.load()]

            await self._emit(
                progress,
                StageStarted(run_id=run_id, emitted_at=_now(), stage="generation"),
            )

            for sample in samples_pyd:
                if run_id in self._cancelled:
                    break
                async with run_context(
                    run_id=run_id,
                    sample_idx=sample.idx,
                    stage="generation",
                ):
                    failed = await self._process_one_sample(
                        sample=sample,
                        request=request,
                        model=model,
                        metrics=metrics,
                        storage=storage,
                        progress=progress,
                        generations=generations,
                        per_sample_results=per_sample_results,
                    )
                    if failed:
                        error_count += 1

            await self._emit(
                progress,
                StageCompleted(
                    run_id=run_id,
                    emitted_at=_now(),
                    stage="scoring",
                    duration_ms=_elapsed_ms(run_started_perf),
                ),
            )

            aggregate_results: list[MetricResult] = []
            for metric in metrics:
                metric_per_sample = [
                    r for r in per_sample_results if r.metric_name == metric.spec.name
                ]
                aggregate_results.append(await metric.aggregate(metric_per_sample))

            primary_metric = aggregate_results[0] if aggregate_results else None
            summary = RunSummary(
                run_id=run_id,
                sample_count=len(samples_pyd),
                error_count=error_count,
                primary_metric_name=(primary_metric.metric_name if primary_metric else None),
                primary_metric_value=primary_metric.value if primary_metric else None,
                duration_ms=_elapsed_ms(run_started_perf),
            )
            telemetry = TelemetryReport(
                run_id=run_id,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                total_duration_ms=_elapsed_ms(run_started_perf),
            )
            await storage.finalize_run(run_id, summary, telemetry)
            result = await storage.get_run(run_id)

            status_label: str
            if run_id in self._cancelled:
                status_label = "cancelled" if not generations else "partial"
            elif error_count > 0:
                status_label = "partial"
            else:
                status_label = "succeeded"

            result = result.model_copy(
                update={
                    "aggregate_metric_results": list(aggregate_results),
                    "status": _status_literal(status_label),
                },
            )

            await self._emit(
                progress,
                RunFinalized(
                    run_id=run_id,
                    emitted_at=_now(),
                    status=_status_literal(status_label),
                ),
            )
            return result
        finally:
            await asyncio.gather(model.close(), return_exceptions=True)
            await asyncio.gather(
                *(m.close() for m in metrics),
                return_exceptions=True,
            )

    async def _emit(
        self,
        progress: ProgressSink | None,
        event: ProgressEvent,
    ) -> None:
        """Forward ``event`` to ``progress`` when a sink is configured.

        :param progress: Optional progress sink.
        :param event: Progress event to forward.
        """
        if progress is None:
            return
        await progress.emit(event)

    async def _process_one_sample(  # — engine-local helper
        self,
        *,
        sample: EvaluationSample,
        request: EvaluationRunRequest,
        model: ModelAdapter,
        metrics: list[Metric],
        storage: StorageAdapter,
        progress: ProgressSink | None,
        generations: list[GenerationResponse],
        per_sample_results: list[MetricResult],
    ) -> bool:
        """Generate, score, persist one sample, and emit progress events.

        :param sample: Dataset row to evaluate.
        :param request: Parent run request (``run_id``, sampling, etc.).
        :param model: Model adapter for generation.
        :param metrics: Built metrics to score with.
        :param storage: Persistence adapter for samples and metric rows.
        :param progress: Optional sink for :class:`ProgressEvent` fan-out.
        :param generations: Mutable list; successful responses are appended.
        :param per_sample_results: Mutable list; per-sample results are appended.

        :return: ``True`` if generation failed and the sample was stored as errored.
        """
        run_id = request.run_id
        sample_started_perf = time.perf_counter()
        await self._emit(
            progress,
            SampleStarted(
                run_id=run_id,
                emitted_at=_now(),
                sample_idx=sample.idx,
                stage="generation",
            ),
        )

        sample_record: SampleRecord
        sample_results: list[MetricResult] = []
        try:
            generation_request = GenerationRequest(
                messages=[ChatMessage(role="user", content=sample.input)],
                sampling=request.sampling,
            )
            response = await generate_for_sample(
                sample=sample,
                model=model,
                sampling=generation_request,
            )
        except Exception as exc:  # — captured into the run.
            sample_record = SampleRecord(
                run_id=run_id,
                idx=sample.idx,
                input=sample.input,
                reference=sample.reference,
                generation=None,
                latency_ms=0.0,
                error=str(exc),
            )
            await storage.append_sample(run_id, sample_record)
            await self._emit(
                progress,
                SampleFailed(
                    run_id=run_id,
                    emitted_at=_now(),
                    sample_idx=sample.idx,
                    stage="generation",
                    exception_class=exc.__class__.__name__,
                    exception_message=str(exc),
                ),
            )
            return True

        with timed("engine.score_for_sample"):
            sample_results = await score_for_sample(
                sample=sample,
                response=response,
                metrics=metrics,
            )
        sample_record = SampleRecord(
            run_id=run_id,
            idx=sample.idx,
            input=sample.input,
            reference=sample.reference,
            generation=response.text,
            latency_ms=response.latency_ms,
        )
        await storage.append_sample(run_id, sample_record)
        for metric_result in sample_results:
            await storage.append_metric_result(
                run_id,
                MetricResultRecord(
                    run_id=run_id,
                    sample_idx=metric_result.sample_idx,
                    metric_name=metric_result.metric_name,
                    metric_version=metric_result.metric_version,
                    status=metric_result.status,
                    value=metric_result.value,
                    sub_values=list(metric_result.sub_values),
                    compute_latency_ms=metric_result.compute_latency_ms,
                    exception_class=metric_result.exception_class,
                    exception_message=metric_result.exception_message,
                ),
            )
        generations.append(response)
        per_sample_results.extend(sample_results)
        await self._emit(
            progress,
            SampleCompleted(
                run_id=run_id,
                emitted_at=_now(),
                sample_idx=sample.idx,
                stage="scoring",
                duration_ms=_elapsed_ms(sample_started_perf),
            ),
        )
        return False


def _now() -> datetime:
    """
    Return the current UTC timestamp.

    :return: A :class:`datetime` instance.
    """
    return datetime.now(UTC)


def _elapsed_ms(start_perf: float) -> float:
    """
    Return elapsed milliseconds since ``start_perf``.

    :param start_perf: ``time.perf_counter()`` value at interval start.

    :return: Elapsed milliseconds since ``start_perf``.
    """
    return (time.perf_counter() - start_perf) * 1000.0


_StatusLiteral = Literal["succeeded", "partial", "failed", "cancelled"]


def _status_literal(label: str) -> _StatusLiteral:
    """
    Map a status label to the engine literal type.

    :param label: Status label from the engine.

    :return: A :class:`_StatusLiteral` instance.
    """
    if label == "succeeded":
        return "succeeded"
    if label == "partial":
        return "partial"
    if label == "cancelled":
        return "cancelled"
    return "failed"
