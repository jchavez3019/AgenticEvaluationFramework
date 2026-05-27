"""Pydantic record models consumed by :class:`StorageAdapter`.

The :class:`StorageAdapter` Protocol (defined in :mod:`backend.persistence.base`)
returns Pydantic instances of these models — never SQLAlchemy ORM rows.
The API layer round-trips these shapes to clients verbatim.

# ADR: Persistence — SQLite Default, Postgres Swap-In
# See: adr/0006-persistence-sqlite-default-postgres-swap-in.md
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from backend.contracts.adapter_spec import (
    DatasetAdapterSpec,
    ModelAdapterSpec,
    ModelCapabilities,
)
from backend.contracts.metric_result import MetricSpec, MetricStatus, SubScore
from backend.contracts.primitives import EngineKind


class RunStatus(StrEnum):
    """Lifecycle states a run can be in (per ADR-0006 §4)."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunRecord(BaseModel):
    """The ``runs`` row projected as Pydantic.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * id: Primary key — same value as ``run_id`` in contracts.
    * title: Optional short label copied from the run request.
    * description: Optional longer description copied from the run request.
    * created_at: UTC timestamp when the run row was inserted.
    * finished_at: UTC timestamp when the run reached a terminal status.
    * status: Current lifecycle state of the run.
    * engine_kind: Whether the run used local or distributed execution.
    * model_spec: Frozen model adapter spec used for the run.
    * dataset_spec: Frozen dataset adapter spec used for the run.
    * metric_specs: Metric specs configured for the run.
    * seed: Global RNG seed stored with the run.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    title: str | None = None
    description: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
    status: RunStatus
    engine_kind: EngineKind
    model_spec: ModelAdapterSpec
    dataset_spec: DatasetAdapterSpec
    metric_specs: list[MetricSpec] = Field(default_factory=list[MetricSpec])
    seed: int = 0


class SampleRecord(BaseModel):
    """The ``samples`` row projected as Pydantic.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * run_id: Foreign key to the parent run.
    * idx: Zero-based sample index within the run.
    * input: Prompt text fed to the model.
    * reference: Gold answer when the dataset provided one.
    * generation: Model output text after the generation stage.
    * latency_ms: Generation latency recorded for this sample.
    * error: Error message when generation or scoring failed for this sample.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    idx: Annotated[int, Field(ge=0)]
    input: str
    reference: str | None = None
    generation: str | None = None
    latency_ms: Annotated[float, Field(ge=0.0)] = 0.0
    error: str | None = None


class MetricResultRecord(BaseModel):
    """The ``metric_results`` row projected as Pydantic.

    Mirrors :class:`MetricResult` but adds the ``run_id`` foreign key.
    Carrying the same shape on both sides means the engine can produce a
    :class:`MetricResult`, hand it to ``append_metric_result(...)``, and
    the storage adapter just adds ``run_id``.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * run_id: Foreign key to the parent run.
    * sample_idx: Sample index for per-sample metrics; ``None`` for aggregates.
    * metric_name: Registry name of the metric.
    * metric_version: Version string of the metric implementation.
    * status: Outcome of the computation (ok, error, or skipped).
    * value: Primary scalar score when produced.
    * sub_values: Named sub-scores when the metric is variadic.
    * compute_latency_ms: Wall-clock compute time for this result.
    * exception_class: Exception type when ``status`` is error.
    * exception_message: Exception message when ``status`` is error.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    sample_idx: Annotated[int | None, Field(ge=0)] = None
    metric_name: str = Field(min_length=1)
    metric_version: str = Field(min_length=1)
    status: MetricStatus
    value: float | None = None
    sub_values: list[SubScore] = Field(default_factory=list[SubScore])
    compute_latency_ms: Annotated[float, Field(ge=0.0)] = 0.0
    exception_class: str | None = None
    exception_message: str | None = None


class RunSummary(BaseModel):
    """Compact per-run rollup written when a run finalizes.

    Stored in ``runs.summary_json`` so the dashboard's Run History card
    can render run-level columns without fetching every metric row.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * run_id: Unique identifier of the run.
    * sample_count: Number of samples processed (or attempted).
    * error_count: Number of samples that failed during the run.
    * primary_metric_name: Name of the headline metric for the run card.
    * primary_metric_value: Aggregate value of the headline metric.
    * duration_ms: Total wall time for the run in milliseconds.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    sample_count: Annotated[int, Field(ge=0)]
    error_count: Annotated[int, Field(ge=0)] = 0
    primary_metric_name: str | None = None
    primary_metric_value: float | None = None
    duration_ms: Annotated[float, Field(ge=0.0)] = 0.0


class RunQuery(BaseModel):
    """Filter / pagination payload for :meth:`StorageAdapter.list_runs`.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * status: Filter to runs in this lifecycle state.
    * engine_kind: Filter to runs executed with this engine kind.
    * model_name: Filter to runs whose model spec name matches.
    * dataset_name: Filter to runs whose dataset spec name matches.
    * text: Case-insensitive substring match on title or description.
    * created_after: Include runs created at or after this timestamp.
    * created_before: Include runs created before this timestamp.
    * page: One-based page index for pagination.
    * limit: Maximum rows per page (capped at 200).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: RunStatus | None = None
    engine_kind: EngineKind | None = None
    model_name: str | None = None
    dataset_name: str | None = None
    text: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    page: Annotated[int, Field(ge=1)] = 1
    limit: Annotated[int, Field(ge=1, le=200)] = 25


class RunListPage(BaseModel):
    """One page of :class:`RunRecord` results.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * items: Run records on this page.
    * page: One-based page index echoed from the query.
    * limit: Page size echoed from the query.
    * total: Total matching runs across all pages.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[RunRecord]
    page: Annotated[int, Field(ge=1)]
    limit: Annotated[int, Field(ge=1)]
    total: Annotated[int, Field(ge=0)]


class ModelMetadataRecord(BaseModel):
    """The ``model_metadata`` row projected as Pydantic.

    Denormalized from the most recent run that referenced the model; the
    Metadata Viewer dashboard card reads exclusively from this table.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * id: Stable metadata row identifier (typically the model spec name).
    * name: Display name of the model adapter.
    * capabilities: Capability flags from the latest seen model spec.
    * description: Optional description from the latest seen model spec.
    * last_seen_at: UTC timestamp when a run last referenced this model.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    capabilities: ModelCapabilities
    description: str | None = None
    last_seen_at: datetime | None = None


class DatasetMetadataRecord(BaseModel):
    """The ``dataset_metadata`` row projected as Pydantic.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * id: Stable metadata row identifier (typically the dataset spec name).
    * name: Display name of the dataset adapter.
    * row_count: Number of rows advertised by the dataset when known.
    * description: Optional description from the latest seen dataset spec.
    * last_seen_at: UTC timestamp when a run last referenced this dataset.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    row_count: Annotated[int | None, Field(ge=0)] = None
    description: str | None = None
    last_seen_at: datetime | None = None
