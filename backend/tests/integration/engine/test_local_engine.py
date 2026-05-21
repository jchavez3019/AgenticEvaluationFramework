"""End-to-end test of :class:`LocalEngine` driven against the mocks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from aef.adapters.models.mocks import MatchAny, MockChatModel, MockChatScript
from aef.adapters.registry import (
    register_model_adapter,
    unregister_model_adapter,
)
from aef.contracts.adapter_spec import (
    DatasetAdapterSpec,
    ModelAdapterSpec,
    ModelCapabilities,
)
from aef.contracts.metric_result import MetricKind, MetricSpec
from aef.contracts.primitives import GenerationConfig
from aef.contracts.run import EvaluationRunRequest
from aef.engine.base import (
    ProgressEvent,
    RunFinalized,
    SampleCompleted,
    StageStarted,
)
from aef.engine.local import LocalEngine

if TYPE_CHECKING:
    from aef.persistence import SQLiteStorage

pytestmark = pytest.mark.asyncio


class _CapturingProgress:
    def __init__(self) -> None:
        self.events: list[ProgressEvent] = []

    async def emit(self, event: ProgressEvent) -> None:
        self.events.append(event)


@pytest.fixture
def scripted_mock_chat() -> object:
    """Register a per-test mock-chat factory that returns the input verbatim."""

    def factory(spec: ModelAdapterSpec) -> MockChatModel:
        return MockChatModel(
            spec,
            scripts=[MockChatScript(match=MatchAny(), response="echo")],
            sleep_for_latency=False,
        )

    unregister_model_adapter("mock-chat")
    register_model_adapter("mock-chat", factory)
    yield
    unregister_model_adapter("mock-chat")
    from aef.adapters.models.mocks import register_default_mocks

    register_default_mocks()


def _request(run_id: str = "run-local-1") -> EvaluationRunRequest:
    return EvaluationRunRequest(
        run_id=run_id,
        model=ModelAdapterSpec(
            name="mock-chat",
            model_id="mock-chat",
            capabilities=ModelCapabilities(),
        ),
        dataset=DatasetAdapterSpec(name="mock", dataset_id="mock"),
        metrics=[
            MetricSpec(name="exact_match", kind=MetricKind.LEXICAL),
            MetricSpec(name="latency", kind=MetricKind.OPERATIONAL),
        ],
        sampling=GenerationConfig(),
    )


async def test_local_engine_completes_with_expected_progress(
    in_memory_storage: SQLiteStorage,
    scripted_mock_chat: object,
) -> None:
    engine = LocalEngine()
    progress = _CapturingProgress()

    result = await engine.run(_request(), in_memory_storage, progress=progress)
    await engine.close()

    assert result.status == "succeeded"
    assert len(result.samples) > 0
    assert any(isinstance(e, StageStarted) for e in progress.events)
    assert any(isinstance(e, SampleCompleted) for e in progress.events)
    assert isinstance(progress.events[-1], RunFinalized)


async def test_local_engine_persists_metric_results(
    in_memory_storage: SQLiteStorage,
    scripted_mock_chat: object,
) -> None:
    engine = LocalEngine()
    result = await engine.run(_request("run-local-2"), in_memory_storage)
    await engine.close()

    assert {m.metric_name for m in result.aggregate_metric_results} == {
        "exact_match",
        "latency",
    }


async def test_local_engine_marks_run_partial_on_sample_failure(
    in_memory_storage: SQLiteStorage,
) -> None:
    """A failing model on every script becomes a ``failed`` (no successes) run."""
    failing = MockChatScript(
        match=MatchAny(),
        response="ignored",
        fail_with="RuntimeError",
    )

    def factory(spec: ModelAdapterSpec) -> MockChatModel:
        return MockChatModel(spec, scripts=[failing], sleep_for_latency=False)

    unregister_model_adapter("mock-chat")
    register_model_adapter("mock-chat", factory)
    try:
        engine = LocalEngine()
        result = await engine.run(_request("run-local-3"), in_memory_storage)
        await engine.close()
        assert result.status == "partial"
    finally:
        unregister_model_adapter("mock-chat")
        from aef.adapters.models.mocks import register_default_mocks

        register_default_mocks()


async def test_cancel_marks_run_cancelled_when_no_samples_succeed(
    in_memory_storage: SQLiteStorage,
    scripted_mock_chat: object,
) -> None:
    engine = LocalEngine()
    await engine.cancel("run-local-4")
    result = await engine.run(_request("run-local-4"), in_memory_storage)
    await engine.close()
    assert result.status == "cancelled"
