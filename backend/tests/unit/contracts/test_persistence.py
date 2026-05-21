"""Round-trip tests for ``aef.contracts.persistence``."""

from __future__ import annotations

from datetime import UTC, datetime

from aef.contracts.adapter_spec import (
    DatasetAdapterSpec,
    ModelAdapterSpec,
    ModelCapabilities,
)
from aef.contracts.metric_result import MetricKind, MetricSpec, MetricStatus, SubScore
from aef.contracts.persistence import (
    DatasetMetadataRecord,
    MetricResultRecord,
    ModelMetadataRecord,
    RunListPage,
    RunQuery,
    RunRecord,
    RunStatus,
    RunSummary,
    SampleRecord,
)


def _make_model_spec() -> ModelAdapterSpec:
    return ModelAdapterSpec(
        name="mock-chat",
        model_id="mock-1",
        capabilities=ModelCapabilities(family="mock"),
    )


def test_run_record_round_trip() -> None:
    record = RunRecord(
        id="run-1",
        title="smoke",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        finished_at=datetime(2026, 1, 1, 0, 0, 5, tzinfo=UTC),
        status=RunStatus.SUCCEEDED,
        engine_kind="local",
        model_spec=_make_model_spec(),
        dataset_spec=DatasetAdapterSpec(name="mock", dataset_id="mock-ds"),
        metric_specs=[MetricSpec(name="bleu", kind=MetricKind.LEXICAL, version="1.0")],
        seed=7,
    )
    rebuilt = RunRecord.model_validate(record.model_dump())
    assert rebuilt == record


def test_sample_record_round_trip() -> None:
    record = SampleRecord(
        run_id="run-1",
        idx=0,
        input="What is 2+2?",
        reference="4",
        generation="4",
        latency_ms=4.5,
    )
    assert SampleRecord.model_validate(record.model_dump()) == record


def test_metric_result_record_round_trip_with_sub_values() -> None:
    record = MetricResultRecord(
        run_id="run-1",
        sample_idx=0,
        metric_name="rouge",
        metric_version="1.0",
        status=MetricStatus.OK,
        value=0.62,
        sub_values=[SubScore(name="rouge_1_f1", value=0.62)],
    )
    assert MetricResultRecord.model_validate(record.model_dump()) == record


def test_run_summary_round_trip() -> None:
    summary = RunSummary(
        run_id="run-1",
        sample_count=10,
        error_count=0,
        primary_metric_name="bleu",
        primary_metric_value=42.5,
        duration_ms=1234.5,
    )
    assert RunSummary.model_validate(summary.model_dump()) == summary


def test_run_query_defaults() -> None:
    query = RunQuery()
    assert query.page == 1
    assert query.limit == 25


def test_run_list_page_round_trip() -> None:
    record = RunRecord(
        id="run-1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        status=RunStatus.SUCCEEDED,
        engine_kind="local",
        model_spec=_make_model_spec(),
        dataset_spec=DatasetAdapterSpec(name="mock", dataset_id="mock-ds"),
    )
    page = RunListPage(items=[record], page=1, limit=25, total=1)
    assert RunListPage.model_validate(page.model_dump()) == page


def test_model_metadata_record_round_trip() -> None:
    meta = ModelMetadataRecord(
        id="huggingface:smollm",
        name="smollm",
        capabilities=ModelCapabilities(
            family="local-hf",
            max_context_tokens=2048,
        ),
        description="Pinned smoke-test model.",
        last_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert ModelMetadataRecord.model_validate(meta.model_dump()) == meta


def test_dataset_metadata_record_round_trip() -> None:
    meta = DatasetMetadataRecord(
        id="mock:mock-ds",
        name="mock-ds",
        row_count=10,
        description="Deterministic in-memory dataset.",
    )
    assert DatasetMetadataRecord.model_validate(meta.model_dump()) == meta
