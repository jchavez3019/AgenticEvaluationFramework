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
    """The ``runs`` row projected as Pydantic."""

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
    """The ``samples`` row projected as Pydantic."""

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
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    sample_count: Annotated[int, Field(ge=0)]
    error_count: Annotated[int, Field(ge=0)] = 0
    primary_metric_name: str | None = None
    primary_metric_value: float | None = None
    duration_ms: Annotated[float, Field(ge=0.0)] = 0.0


class RunQuery(BaseModel):
    """Filter / pagination payload for :meth:`StorageAdapter.list_runs`."""

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
    """One page of :class:`RunRecord` results."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[RunRecord]
    page: Annotated[int, Field(ge=1)]
    limit: Annotated[int, Field(ge=1)]
    total: Annotated[int, Field(ge=0)]


class ModelMetadataRecord(BaseModel):
    """The ``model_metadata`` row projected as Pydantic.

    Denormalized from the most recent run that referenced the model; the
    Metadata Viewer dashboard card reads exclusively from this table.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    capabilities: ModelCapabilities
    description: str | None = None
    last_seen_at: datetime | None = None


class DatasetMetadataRecord(BaseModel):
    """The ``dataset_metadata`` row projected as Pydantic."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    row_count: Annotated[int | None, Field(ge=0)] = None
    description: str | None = None
    last_seen_at: datetime | None = None
