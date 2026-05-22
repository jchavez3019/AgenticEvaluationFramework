"""SQLAlchemy 2.x typed declarative ORM models.

Schema follows ADR-0006 §4 verbatim. Every column uses
:func:`mapped_column` with explicit :class:`Mapped[T]` annotations so
Pyright can verify queries at type-check time.

# ADR: Persistence — SQLite Default, Postgres Swap-In
# See: adr/0006-persistence-sqlite-default-postgres-swap-in.md
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


def _utcnow() -> datetime:
    """
    Return a timezone-aware UTC ``datetime`` for default columns.

    :return: ``datetime`` result.
    """
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Single declarative base for every ORM model in the framework."""


class Run(Base):
    """``runs`` table — one row per evaluation."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    engine_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    seed: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)

    # JSON-as-text columns (per ADR-0006 §4 — portable across SQLite + Postgres).
    model_spec_json: Mapped[str] = mapped_column(Text(), nullable=False)
    dataset_spec_json: Mapped[str] = mapped_column(Text(), nullable=False)
    metric_specs_json: Mapped[str] = mapped_column(Text(), nullable=False)
    summary_json: Mapped[str | None] = mapped_column(Text(), nullable=True)

    samples: Mapped[list[Sample]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )
    metric_results: Mapped[list[MetricResult]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )
    telemetry: Mapped[RunTelemetry | None] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Sample(Base):
    """``samples`` table — one row per (run, sample-index)."""

    __tablename__ = "samples"
    __table_args__ = (UniqueConstraint("run_id", "idx", name="uq_samples_run_idx"),)

    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    idx: Mapped[int] = mapped_column(Integer(), primary_key=True)
    input: Mapped[str] = mapped_column(Text(), nullable=False)
    reference: Mapped[str | None] = mapped_column(Text(), nullable=True)
    generation: Mapped[str | None] = mapped_column(Text(), nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float(), nullable=False, default=0.0)
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)

    run: Mapped[Run] = relationship(back_populates="samples")


class MetricResult(Base):
    """``metric_results`` table — one row per metric-per-sample (or per run)."""

    __tablename__ = "metric_results"

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sample_idx: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    metric_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[float | None] = mapped_column(Float(), nullable=True)
    sub_values_json: Mapped[str | None] = mapped_column(Text(), nullable=True)
    compute_latency_ms: Mapped[float] = mapped_column(
        Float(),
        nullable=False,
        default=0.0,
    )
    exception_class: Mapped[str | None] = mapped_column(String(128), nullable=True)
    exception_message: Mapped[str | None] = mapped_column(Text(), nullable=True)

    run: Mapped[Run] = relationship(back_populates="metric_results")


class RunTelemetry(Base):
    """``run_telemetry`` table — JSON :class:`TelemetryReport` keyed by run."""

    __tablename__ = "run_telemetry"

    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    report_json: Mapped[str] = mapped_column(Text(), nullable=False)

    run: Mapped[Run] = relationship(back_populates="telemetry")


class ModelMetadata(Base):
    """``model_metadata`` table — denormalized cache for the dashboard."""

    __tablename__ = "model_metadata"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    capabilities_json: Mapped[str] = mapped_column(Text(), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class DatasetMetadata(Base):
    """``dataset_metadata`` table — denormalized cache for the dashboard."""

    __tablename__ = "dataset_metadata"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
