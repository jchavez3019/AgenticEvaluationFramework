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

from aef.contracts.primitives import PipelineStage


class TimingRecord(BaseModel):
    """One ``with timed("phase"):`` entry recorded by the engine."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: str = Field(min_length=1)
    duration_ms: Annotated[float, Field(ge=0.0)]
    sample_idx: Annotated[int | None, Field(ge=0)] = None
    stage: PipelineStage
    exception_class: str | None = None


class StageSummary(BaseModel):
    """Per-stage rollup computed at run finalize."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: PipelineStage
    total_ms: Annotated[float, Field(ge=0.0)]
    samples_processed: Annotated[int, Field(ge=0)]
    p50_ms: Annotated[float, Field(ge=0.0)]
    p95_ms: Annotated[float, Field(ge=0.0)]
    p99_ms: Annotated[float, Field(ge=0.0)]
    error_count: Annotated[int, Field(ge=0)]


class QueueDepthSample(BaseModel):
    """Periodic snapshot of an engine queue's depth."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    queue_name: str = Field(min_length=1)
    depth: Annotated[int, Field(ge=0)]
    captured_at: datetime


class ThroughputCounters(BaseModel):
    """Run-level throughput rollup."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    generation_tokens_per_sec: float | None = None
    scoring_samples_per_sec: float | None = None
    queue_depths: list[QueueDepthSample] = Field(
        default_factory=list[QueueDepthSample],
    )


class TelemetryReport(BaseModel):
    """Top-level telemetry block landed inside ``EvaluationRunResult``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    started_at: datetime
    finished_at: datetime
    total_duration_ms: Annotated[float, Field(ge=0.0)]
    per_record: list[TimingRecord] = Field(default_factory=list[TimingRecord])
    per_stage: list[StageSummary] = Field(default_factory=list[StageSummary])
    counters: ThroughputCounters = Field(default_factory=ThroughputCounters)
