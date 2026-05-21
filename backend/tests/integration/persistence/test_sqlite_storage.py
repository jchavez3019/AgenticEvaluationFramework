"""Round-trip and behavior tests for :class:`SQLiteStorage`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aef.contracts.adapter_spec import (
    DatasetAdapterSpec,
    ModelAdapterSpec,
    ModelCapabilities,
)
from aef.contracts.metric_result import MetricKind, MetricSpec, MetricStatus
from aef.contracts.persistence import (
    DatasetMetadataRecord,
    MetricResultRecord,
    ModelMetadataRecord,
    RunQuery,
    RunStatus,
    RunSummary,
    SampleRecord,
)
from aef.contracts.run import EvaluationRunRequest
from aef.contracts.telemetry import TelemetryReport
from aef.persistence import SQLiteStorage


def _request(run_id: str = "run-001") -> EvaluationRunRequest:
    return EvaluationRunRequest(
        run_id=run_id,
        title="round-trip",
        description="storage smoke",
        model=ModelAdapterSpec(
            name="mock-chat",
            model_id="mock-chat-id",
            capabilities=ModelCapabilities(family="mock"),
            config={"api_key": "sk-leak", "model_id": "mock-chat-id"},
        ),
        dataset=DatasetAdapterSpec(name="mock", dataset_id="mock-id"),
        metrics=[
            MetricSpec(
                name="exact_match",
                kind=MetricKind.LEXICAL,
            ),
        ],
    )


async def test_create_and_get_run_round_trip(
    in_memory_storage: SQLiteStorage,
) -> None:
    request = _request()
    record = await in_memory_storage.create_run(request)
    assert record.id == "run-001"
    assert record.status == RunStatus.PENDING

    sample = SampleRecord(
        run_id="run-001",
        idx=0,
        input="hi",
        reference="hello",
        generation="hello",
        latency_ms=12.0,
    )
    await in_memory_storage.append_sample("run-001", sample)

    metric = MetricResultRecord(
        run_id="run-001",
        sample_idx=0,
        metric_name="exact_match",
        metric_version="1.0",
        status=MetricStatus.OK,
        value=1.0,
        compute_latency_ms=0.5,
    )
    await in_memory_storage.append_metric_result("run-001", metric)

    summary = RunSummary(
        run_id="run-001",
        sample_count=1,
        primary_metric_name="exact_match",
        primary_metric_value=1.0,
        duration_ms=12.5,
    )
    started = datetime.now(UTC)
    telemetry = TelemetryReport(
        run_id="run-001",
        started_at=started,
        finished_at=started,
        total_duration_ms=0.0,
    )
    result = await in_memory_storage.finalize_run("run-001", summary, telemetry)

    assert result.run_id == "run-001"
    assert result.status == "succeeded"
    assert len(result.samples) == 1
    assert result.samples[0].input == "hi"
    assert len(result.metric_results) == 1
    assert result.metric_results[0].value == 1.0


async def test_secrets_are_redacted_in_persisted_spec(
    in_memory_storage: SQLiteStorage,
) -> None:
    request = _request("run-redact")
    await in_memory_storage.create_run(request)
    fetched = await in_memory_storage.get_run("run-redact")
    assert fetched.request.model.config["api_key"] == "<redacted>"
    assert fetched.request.model.config["model_id"] == "mock-chat-id"


async def test_get_run_unknown_raises_keyerror(
    in_memory_storage: SQLiteStorage,
) -> None:
    with pytest.raises(KeyError, match="not found"):
        await in_memory_storage.get_run("does-not-exist")


async def test_list_runs_filters_and_paginates(
    in_memory_storage: SQLiteStorage,
) -> None:
    for i in range(7):
        request = _request(run_id=f"run-{i:03d}")
        await in_memory_storage.create_run(request)

    page = await in_memory_storage.list_runs(RunQuery(page=1, limit=3))
    assert page.total == 7
    assert page.page == 1
    assert page.limit == 3
    assert len(page.items) == 3

    page2 = await in_memory_storage.list_runs(RunQuery(page=2, limit=3))
    assert page2.page == 2
    assert len(page2.items) == 3


async def test_delete_run_cascades(
    in_memory_storage: SQLiteStorage,
) -> None:
    request = _request("run-del")
    await in_memory_storage.create_run(request)
    await in_memory_storage.append_sample(
        "run-del",
        SampleRecord(run_id="run-del", idx=0, input="x"),
    )
    await in_memory_storage.delete_run("run-del")
    with pytest.raises(KeyError):
        await in_memory_storage.get_run("run-del")


async def test_foreign_key_violation_raises(
    in_memory_storage: SQLiteStorage,
) -> None:
    """Inserting a sample whose run does not exist must fail."""
    from sqlalchemy.exc import IntegrityError

    sample = SampleRecord(run_id="nope", idx=0, input="x")
    with pytest.raises(IntegrityError):
        await in_memory_storage.append_sample("nope", sample)


async def test_partial_status_when_summary_has_errors(
    in_memory_storage: SQLiteStorage,
) -> None:
    request = _request("run-partial")
    await in_memory_storage.create_run(request)
    started = datetime.now(UTC)
    summary = RunSummary(run_id="run-partial", sample_count=2, error_count=1)
    telemetry = TelemetryReport(
        run_id="run-partial",
        started_at=started,
        finished_at=started,
        total_duration_ms=0.0,
    )
    result = await in_memory_storage.finalize_run("run-partial", summary, telemetry)
    assert result.status == "partial"


async def test_metadata_upsert_and_list(
    in_memory_storage: SQLiteStorage,
) -> None:
    model_meta = ModelMetadataRecord(
        id="mock-chat-id",
        name="mock-chat",
        capabilities=ModelCapabilities(family="mock"),
    )
    await in_memory_storage.upsert_model_metadata(model_meta)
    fetched = await in_memory_storage.list_model_metadata()
    assert len(fetched) == 1
    assert fetched[0].name == "mock-chat"

    updated = ModelMetadataRecord(
        id="mock-chat-id",
        name="mock-chat-renamed",
        capabilities=ModelCapabilities(family="mock"),
    )
    await in_memory_storage.upsert_model_metadata(updated)
    fetched = await in_memory_storage.list_model_metadata()
    assert len(fetched) == 1
    assert fetched[0].name == "mock-chat-renamed"

    dataset_meta = DatasetMetadataRecord(
        id="mock-id",
        name="mock",
        row_count=5,
    )
    await in_memory_storage.upsert_dataset_metadata(dataset_meta)
    datasets = await in_memory_storage.list_dataset_metadata()
    assert len(datasets) == 1
    assert datasets[0].row_count == 5


async def test_storage_satisfies_protocol() -> None:
    """:class:`SQLiteStorage` must structurally satisfy :class:`StorageAdapter`."""
    from aef.persistence.base import StorageAdapter

    storage = SQLiteStorage.from_url("sqlite+aiosqlite:///:memory:")
    assert isinstance(storage, StorageAdapter)
    await storage.close()
