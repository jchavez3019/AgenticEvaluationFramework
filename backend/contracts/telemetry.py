"""Telemetry shapes — the data block recorded at every run finalize.

The :class:`TelemetryReport` is the source of truth for the run's timing
profile. It serializes verbatim to ``EvaluationRunResult.telemetry`` and
to the ``run_telemetry.report`` JSON column in SQLite (per ADR-0006 §4).

# ADR: Logging and Telemetry Contract
# See: adr/0012-logging-and-telemetry-contract.md
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from backend.contracts.primitives import PipelineStage


class TimingRecord(BaseModel):
    """One ``with timed("phase"):`` entry recorded by the engine.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * phase: Logical phase name within a stage (for example ``adapter.generate``).
    * duration_ms: Elapsed milliseconds for this timed block.
    * sample_idx: Sample index when the timing is per-sample; ``None`` for run-level.
    * stage: Pipeline stage active when the block ran.
    * exception_class: Exception type when the timed block failed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: str = Field(min_length=1)
    duration_ms: Annotated[float, Field(ge=0.0)]
    sample_idx: Annotated[int | None, Field(ge=0)] = None
    stage: PipelineStage
    exception_class: str | None = None


class StageSummary(BaseModel):
    """Per-stage rollup computed at run finalize.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * stage: Pipeline stage this summary aggregates.
    * total_ms: Total wall time spent in this stage across the run.
    * samples_processed: Number of samples that entered this stage.
    * p50_ms: Median per-sample duration within the stage.
    * p95_ms: 95th percentile per-sample duration within the stage.
    * p99_ms: 99th percentile per-sample duration within the stage.
    * error_count: Number of failures recorded during this stage.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: PipelineStage
    total_ms: Annotated[float, Field(ge=0.0)]
    samples_processed: Annotated[int, Field(ge=0)]
    p50_ms: Annotated[float, Field(ge=0.0)]
    p95_ms: Annotated[float, Field(ge=0.0)]
    p99_ms: Annotated[float, Field(ge=0.0)]
    error_count: Annotated[int, Field(ge=0)]


class QueueDepthSample(BaseModel):
    """Periodic snapshot of an engine queue's depth.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * queue_name: Engine queue identifier (generation, scoring_cpu, scoring_judge).
    * depth: Number of tasks waiting in the queue at capture time.
    * captured_at: UTC timestamp when the snapshot was taken.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    queue_name: str = Field(min_length=1)
    depth: Annotated[int, Field(ge=0)]
    captured_at: datetime


class ThroughputCounters(BaseModel):
    """Run-level throughput rollup.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * generation_tokens_per_sec: Average generation throughput when measurable.
    * scoring_samples_per_sec: Average scoring throughput when measurable.
    * queue_depths: Time series of queue depth snapshots during the run.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    generation_tokens_per_sec: float | None = None
    scoring_samples_per_sec: float | None = None
    queue_depths: list[QueueDepthSample] = Field(
        default_factory=list[QueueDepthSample],
    )


class TelemetryReport(BaseModel):
    """Top-level telemetry block landed inside ``EvaluationRunResult``.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * run_id: Unique identifier of the evaluation run.
    * started_at: UTC timestamp when the run began.
    * finished_at: UTC timestamp when the run completed or was cancelled.
    * total_duration_ms: End-to-end wall time for the run in milliseconds.
    * per_record: Raw timing records collected during execution.
    * per_stage: Rollups derived from ``per_record`` at finalize time.
    * counters: Throughput and queue-depth counters for the run.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    started_at: datetime
    finished_at: datetime
    total_duration_ms: Annotated[float, Field(ge=0.0)]
    per_record: list[TimingRecord] = Field(default_factory=list[TimingRecord])
    per_stage: list[StageSummary] = Field(default_factory=list[StageSummary])
    counters: ThroughputCounters = Field(default_factory=ThroughputCounters)
