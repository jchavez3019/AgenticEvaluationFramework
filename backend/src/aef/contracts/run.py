"""Top-level run request / result shapes.

This module composes the leaf primitives (:mod:`aef.contracts.primitives`),
adapter specs (:mod:`aef.contracts.adapter_spec`), metric models
(:mod:`aef.contracts.metric_result`), and telemetry
(:mod:`aef.contracts.telemetry`) into the two top-level Pydantic models the
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

from aef.contracts.adapter_spec import (
    DatasetAdapterSpec,
    JudgeAdapterSpec,
    ModelAdapterSpec,
)
from aef.contracts.metric_result import MetricResult, MetricSpec
from aef.contracts.primitives import (
    EngineConfig,
    EvaluationSample,
    GenerationConfig,
    GenerationResponse,
    OutputConfig,
)
from aef.contracts.telemetry import TelemetryReport


class EvaluationRunRequest(BaseModel):
    """Everything needed to launch one evaluation run.

    The CLI, the API, and library callers all build instances of this
    model. The model itself is engine-agnostic — :class:`EngineConfig`
    decides whether the run executes locally or on a Celery cluster.
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

    The same model serializes to both ``outputs/cli/<...>/result.json``
    and the ``runs.summary_json`` column in SQLite (per ADR-0006). The
    API returns it verbatim through :class:`StorageAdapter.get_run`.
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
