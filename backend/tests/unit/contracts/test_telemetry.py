"""Round-trip and validator tests for ``backend.contracts.telemetry``."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.contracts.telemetry import (
    QueueDepthSample,
    StageSummary,
    TelemetryReport,
    ThroughputCounters,
    TimingRecord,
)


def test_timing_record_round_trip() -> None:
    """Verify timing record round trip."""
    rec = TimingRecord(
        phase="metric.bleu",
        duration_ms=12.5,
        sample_idx=3,
        stage="scoring",
    )
    assert TimingRecord.model_validate(rec.model_dump()) == rec


def test_timing_record_carries_exception_class() -> None:
    """Verify timing record carries exception class."""
    rec = TimingRecord(
        phase="generation",
        duration_ms=42.0,
        sample_idx=0,
        stage="generation",
        exception_class="ContextOverflowError",
    )
    assert TimingRecord.model_validate(rec.model_dump()) == rec


def test_stage_summary_round_trip() -> None:
    """Verify stage summary round trip."""
    summary = StageSummary(
        stage="generation",
        total_ms=100.0,
        samples_processed=5,
        p50_ms=18.0,
        p95_ms=30.0,
        p99_ms=33.0,
        error_count=0,
    )
    assert StageSummary.model_validate(summary.model_dump()) == summary


def test_queue_depth_sample_round_trip() -> None:
    """Verify queue depth sample round trip."""
    sample = QueueDepthSample(
        queue_name="generation",
        depth=4,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert QueueDepthSample.model_validate(sample.model_dump()) == sample


def test_telemetry_report_round_trip() -> None:
    """Verify telemetry report round trip."""
    started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    finished = datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC)
    report = TelemetryReport(
        run_id="run-1",
        started_at=started,
        finished_at=finished,
        total_duration_ms=1000.0,
        per_record=[
            TimingRecord(
                phase="metric.bleu",
                duration_ms=12.5,
                sample_idx=0,
                stage="scoring",
            ),
        ],
        per_stage=[
            StageSummary(
                stage="scoring",
                total_ms=12.5,
                samples_processed=1,
                p50_ms=12.5,
                p95_ms=12.5,
                p99_ms=12.5,
                error_count=0,
            ),
        ],
        counters=ThroughputCounters(
            generation_tokens_per_sec=100.0,
            scoring_samples_per_sec=10.0,
        ),
    )
    rebuilt = TelemetryReport.model_validate(report.model_dump())
    assert rebuilt == report
