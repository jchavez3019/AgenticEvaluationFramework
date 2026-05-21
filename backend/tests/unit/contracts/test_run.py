"""Round-trip and golden-snapshot tests for ``aef.contracts.run``."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from aef.contracts.adapter_spec import (
    DatasetAdapterSpec,
    ModelAdapterSpec,
    ModelCapabilities,
)
from aef.contracts.metric_result import MetricKind, MetricResult, MetricSpec, MetricStatus
from aef.contracts.primitives import (
    ChatMessage,
    EvaluationSample,
    GenerationConfig,
    GenerationRequest,
    GenerationResponse,
    SampleMetadata,
    Usage,
)
from aef.contracts.run import EvaluationRunRequest, EvaluationRunResult
from aef.contracts.telemetry import (
    StageSummary,
    TelemetryReport,
    ThroughputCounters,
    TimingRecord,
)

GOLDEN_DIR = Path(__file__).parent.parent.parent / "fixtures" / "golden"


def _make_request(*, run_id: str = "run-golden") -> EvaluationRunRequest:
    return EvaluationRunRequest(
        run_id=run_id,
        title="walking-skeleton smoke run",
        seed=0,
        model=ModelAdapterSpec(
            name="mock-chat",
            model_id="mock-chat-1",
            capabilities=ModelCapabilities(
                family="mock",
                supported_sampling_parameters=frozenset({"temperature", "seed"}),
            ),
        ),
        dataset=DatasetAdapterSpec(
            name="mock",
            dataset_id="mock-ds-1",
            row_count=2,
            provides=frozenset({"reference"}),
        ),
        metrics=[
            MetricSpec(
                name="exact_match",
                kind=MetricKind.LEXICAL,
                version="1.0",
                required_inputs=frozenset({"reference"}),
            ),
        ],
        sampling=GenerationConfig(temperature=0.0, seed=0),
    )


def _make_result(*, request: EvaluationRunRequest) -> EvaluationRunResult:
    started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    finished = datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC)
    return EvaluationRunResult(
        run_id=request.run_id,
        status="succeeded",
        started_at=started,
        finished_at=finished,
        request=request,
        samples=[
            EvaluationSample(
                idx=0,
                input="What is 2+2?",
                reference="4",
                metadata=SampleMetadata(dataset_split="test"),
            ),
        ],
        generations=[
            GenerationResponse(
                text="4",
                finish_reason="stop",
                usage=Usage(prompt_tokens=4, completion_tokens=1, total_tokens=5),
                latency_ms=2.5,
            ),
        ],
        metric_results=[
            MetricResult(
                metric_name="exact_match",
                metric_version="1.0",
                sample_idx=0,
                status=MetricStatus.OK,
                value=1.0,
                compute_latency_ms=0.1,
            ),
        ],
        aggregate_metric_results=[
            MetricResult(
                metric_name="exact_match",
                metric_version="1.0",
                status=MetricStatus.OK,
                value=1.0,
            ),
        ],
        telemetry=TelemetryReport(
            run_id=request.run_id,
            started_at=started,
            finished_at=finished,
            total_duration_ms=1000.0,
            per_record=[
                TimingRecord(
                    phase="generation",
                    duration_ms=2.5,
                    sample_idx=0,
                    stage="generation",
                ),
                TimingRecord(
                    phase="metric.exact_match",
                    duration_ms=0.1,
                    sample_idx=0,
                    stage="scoring",
                ),
            ],
            per_stage=[
                StageSummary(
                    stage="generation",
                    total_ms=2.5,
                    samples_processed=1,
                    p50_ms=2.5,
                    p95_ms=2.5,
                    p99_ms=2.5,
                    error_count=0,
                ),
            ],
            counters=ThroughputCounters(
                generation_tokens_per_sec=400.0,
                scoring_samples_per_sec=10000.0,
            ),
        ),
    )


def test_evaluation_run_request_round_trip() -> None:
    req = _make_request()
    rebuilt = EvaluationRunRequest.model_validate(req.model_dump())
    assert rebuilt == req


def test_evaluation_run_request_serializes_generation_config_verbatim() -> None:
    req = _make_request()
    dumped = req.model_dump()
    assert dumped["sampling"]["temperature"] == 0.0
    assert dumped["sampling"]["seed"] == 0
    assert dumped["sampling"]["top_k"] is None


def test_chat_message_inside_generation_request_round_trip() -> None:
    gr = GenerationRequest(
        messages=[
            ChatMessage(role="system", content="Be concise."),
            ChatMessage(role="user", content="What is 2+2?"),
        ],
        sampling=GenerationConfig(temperature=0.5),
    )
    assert GenerationRequest.model_validate(gr.model_dump()) == gr


def test_evaluation_run_result_round_trip() -> None:
    req = _make_request()
    result = _make_result(request=req)
    rebuilt = EvaluationRunResult.model_validate(result.model_dump())
    assert rebuilt == result


def test_evaluation_run_result_matches_golden_snapshot() -> None:
    """Lock the JSON wire shape of an :class:`EvaluationRunResult`.

    On first run, missing the golden file will create it. Subsequent runs
    must match it byte-for-byte.
    """
    req = _make_request()
    result = _make_result(request=req)
    payload = json.loads(result.model_dump_json())

    golden_path = GOLDEN_DIR / "run_result.json"
    if not golden_path.exists():
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    expected = json.loads(golden_path.read_text())
    assert payload == expected, (
        "EvaluationRunResult shape diverged from the golden snapshot. "
        "Update fixtures/golden/run_result.json deliberately if intended."
    )
