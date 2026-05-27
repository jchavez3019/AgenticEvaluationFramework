"""Top-level run request / result shapes.

This module composes the leaf primitives (:mod:`backend.contracts.primitives`),
adapter specs (:mod:`backend.contracts.adapter_spec`), metric models
(:mod:`backend.contracts.metric_result`), and telemetry
(:mod:`backend.contracts.telemetry`) into the two top-level Pydantic models the
CLI, API, and library callers exchange:

- :class:`EvaluationRunRequest` — what a caller submits.
- :class:`EvaluationRunResult` — what :meth:`ExecutionEngine.run` returns.

# ADR: Adapter Architecture for Models and Datasets
# See: adr/0003-adapter-architecture-for-models-and-datasets.md
# ADR: Execution Engine — Local and Distributed
# See: adr/0005-execution-engine-local-and-distributed.md
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.contracts.adapter_spec import (
    DatasetAdapterSpec,
    JudgeAdapterSpec,
    ModelAdapterSpec,
)
from backend.contracts.metric_result import MetricResult, MetricSpec
from backend.contracts.primitives import (
    EngineConfig,
    EvaluationSample,
    GenerationConfig,
    GenerationResponse,
    OutputConfig,
)
from backend.contracts.telemetry import TelemetryReport


class EvaluationRunRequest(BaseModel):
    """Everything needed to launch one evaluation run.

    The CLI, the API, and library callers all build instances of this
    model. The model itself is engine-agnostic — :class:`EngineConfig`
    decides whether the run executes locally or on a Celery cluster.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * run_id: Unique identifier for this run (generated when omitted).
    * title: Optional short label shown in run history UIs.
    * description: Optional longer description of the experiment.
    * seed: Global RNG seed for reproducible sampling across the run.
    * model: Spec of the model adapter under test.
    * judge: Optional judge adapter spec for LLM-as-judge metrics.
    * dataset: Spec of the dataset adapter supplying samples.
    * metrics: Ordered list of metric specs to compute for each sample.
    * sampling: Default generation parameters applied during the run.
    * engine: Local vs distributed execution and queue sizing.
    * output: Artifact paths and which files to write after finalize.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    title: str | None = None
    description: str | None = None
    seed: Annotated[int, Field(ge=0)] = 0
    model: ModelAdapterSpec
    judge: JudgeAdapterSpec | None = None
    dataset: DatasetAdapterSpec
    metrics: list[MetricSpec] = Field(min_length=1)
    sampling: GenerationConfig = Field(default_factory=GenerationConfig)
    engine: EngineConfig = Field(default_factory=EngineConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)


class EvaluationRunResult(BaseModel):
    """The fully-populated result returned by :meth:`ExecutionEngine.run`.

    Serializes to ``result.json`` on disk and to persistence per ADR-0006.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * run_id: Unique identifier matching :attr:`EvaluationRunRequest.run_id`.
    * status: Terminal outcome (succeeded, partial, failed, or cancelled).
    * started_at: UTC timestamp when execution began.
    * finished_at: UTC timestamp when execution completed.
    * request: Frozen copy of the request that drove this run.
    * samples: Dataset rows processed during the run.
    * generations: Model outputs aligned with ``samples`` by index.
    * metric_results: Per-sample metric outputs.
    * aggregate_metric_results: Run-level rollups derived from per-sample metrics.
    * telemetry: Timing profile and throughput counters for the run.
    * error: Top-level error message when ``status`` is failed or partial.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    status: Literal["succeeded", "partial", "failed", "cancelled"]
    started_at: datetime
    finished_at: datetime
    request: EvaluationRunRequest
    samples: list[EvaluationSample] = Field(default_factory=list[EvaluationSample])
    generations: list[GenerationResponse] = Field(
        default_factory=list[GenerationResponse],
    )
    metric_results: list[MetricResult] = Field(default_factory=list[MetricResult])
    aggregate_metric_results: list[MetricResult] = Field(
        default_factory=list[MetricResult],
    )
    telemetry: TelemetryReport
    error: str | None = None
