"""Sanity checks on the typed progress event hierarchy."""

from __future__ import annotations

from datetime import UTC, datetime

from aef.engine.base import (
    ProgressEvent,
    RunFinalized,
    SampleCompleted,
    SampleFailed,
    SampleStarted,
    StageCompleted,
    StageStarted,
)


def _now() -> datetime:
    return datetime(2026, 5, 17, tzinfo=UTC)


def test_each_event_has_a_distinct_kind_tag() -> None:
    events: list[ProgressEvent] = [
        StageStarted(run_id="r", emitted_at=_now(), stage="generation"),
        StageCompleted(
            run_id="r",
            emitted_at=_now(),
            stage="generation",
            duration_ms=1.0,
        ),
        SampleStarted(
            run_id="r",
            emitted_at=_now(),
            sample_idx=0,
            stage="generation",
        ),
        SampleCompleted(
            run_id="r",
            emitted_at=_now(),
            sample_idx=0,
            stage="scoring",
            duration_ms=2.0,
        ),
        SampleFailed(
            run_id="r",
            emitted_at=_now(),
            sample_idx=0,
            stage="generation",
            exception_class="RuntimeError",
            exception_message="boom",
        ),
        RunFinalized(run_id="r", emitted_at=_now(), status="succeeded"),
    ]
    kinds = [e.kind for e in events]
    assert len(set(kinds)) == len(kinds)


def test_events_are_immutable() -> None:
    event = StageStarted(run_id="r", emitted_at=_now(), stage="generation")
    assert event.model_config.get("frozen") is True


def test_run_finalized_constrains_status() -> None:
    RunFinalized(run_id="r", emitted_at=_now(), status="succeeded")
    RunFinalized(run_id="r", emitted_at=_now(), status="partial")
    RunFinalized(run_id="r", emitted_at=_now(), status="failed")
    RunFinalized(run_id="r", emitted_at=_now(), status="cancelled")
