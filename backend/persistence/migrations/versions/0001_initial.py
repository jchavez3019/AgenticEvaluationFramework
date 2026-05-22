"""Initial schema — runs, samples, metric_results, run_telemetry, model_metadata, dataset_metadata.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-20

# ADR: Persistence — SQLite Default, Postgres Swap-In
# See: adr/0006-persistence-sqlite-default-postgres-swap-in.md
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Create the six initial tables."""
    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.String(length=256), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("engine_kind", sa.String(length=32), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_spec_json", sa.Text(), nullable=False),
        sa.Column("dataset_spec_json", sa.Text(), nullable=False),
        sa.Column("metric_specs_json", sa.Text(), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=True),
    )

    op.create_table(
        "samples",
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("generation", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("run_id", "idx", name="pk_samples"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            ondelete="CASCADE",
            name="fk_samples_runs",
        ),
        sa.UniqueConstraint("run_id", "idx", name="uq_samples_run_idx"),
    )

    op.create_table(
        "metric_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("sample_idx", sa.Integer(), nullable=True),
        sa.Column("metric_name", sa.String(length=128), nullable=False, index=True),
        sa.Column("metric_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("sub_values_json", sa.Text(), nullable=True),
        sa.Column(
            "compute_latency_ms",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("exception_class", sa.String(length=128), nullable=True),
        sa.Column("exception_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            ondelete="CASCADE",
            name="fk_metric_results_runs",
        ),
    )

    op.create_table(
        "run_telemetry",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("report_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            ondelete="CASCADE",
            name="fk_run_telemetry_runs",
        ),
    )

    op.create_table(
        "model_metadata",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("capabilities_json", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "dataset_metadata",
        sa.Column("id", sa.String(length=128), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Drop every table created by ``upgrade``."""
    op.drop_table("dataset_metadata")
    op.drop_table("model_metadata")
    op.drop_table("run_telemetry")
    op.drop_table("metric_results")
    op.drop_table("samples")
    op.drop_table("runs")
