"""End-to-end test of :class:`LocalEngine` driven against the mocks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from backend.adapters.models.mocks import MatchAny, MockChatModel, MockChatScript
from backend.adapters.registry import (
    register_model_adapter,
    unregister_model_adapter,
)
from backend.contracts.adapter_spec import (
    DatasetAdapterSpec,
    ModelAdapterSpec,
    ModelCapabilities,
)
from backend.contracts.metric_result import MetricKind, MetricSpec
from backend.contracts.primitives import GenerationConfig
from backend.contracts.run import EvaluationRunRequest
from backend.engine.base import (
    ProgressEvent,
    RunFinalized,
    SampleCompleted,
    StageStarted,
)
from backend.engine.local import LocalEngine

if TYPE_CHECKING:
    from backend.persistence import SQLiteStorage

pytestmark = pytest.mark.asyncio


class _CapturingProgress:
    """Collect :class:`ProgressEvent` instances emitted during a run."""

    def __init__(self) -> None:
        """Initialize an empty event list."""
        self.events: list[ProgressEvent] = []

    async def emit(self, event: ProgressEvent) -> None:
        """
        Emit.

        :param event: Progress event to forward.

        :return: The None result.
        """
        self.events.append(event)


@pytest.fixture
def scripted_mock_chat() -> object:
    """
    Register a per-test mock-chat factory that returns the input verbatim.

    :return: ``object`` result.
    """

    def factory(spec: ModelAdapterSpec) -> MockChatModel:
        """Build a :class:`MockChatModel` for registry override tests.

        :param spec: Adapter or metric specification.

        :return: Configured mock chat model instance.
        """
        return MockChatModel(
            spec,
            scripts=[MockChatScript(match=MatchAny(), response="echo")],
            sleep_for_latency=False,
        )

    unregister_model_adapter("mock-chat")
    register_model_adapter("mock-chat", factory)
    yield
    unregister_model_adapter("mock-chat")
    from backend.adapters.models.mocks import register_default_mocks

    register_default_mocks()


def _request(run_id: str = "run-local-1") -> EvaluationRunRequest:
    """
    Request.

    :param run_id: Unique run identifier.

    :return: A :class:`EvaluationRunRequest` instance.
    """
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
    """
    Verify local engine completes with expected progress.

    :param in_memory_storage: The in memory storage.
    :param scripted_mock_chat: The scripted mock chat.
    """
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
    """
    Verify local engine persists metric results.

    :param in_memory_storage: The in memory storage.
    :param scripted_mock_chat: The scripted mock chat.
    """
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
    """
    A failing model on every script becomes a ``failed`` (no successes) run.

    :param in_memory_storage: In-memory SQLite storage fixture.

    :return: :class:`None` instance.
    """
    failing = MockChatScript(
        match=MatchAny(),
        response="ignored",
        fail_with="RuntimeError",
    )

    def factory(spec: ModelAdapterSpec) -> MockChatModel:
        """Build a :class:`MockChatModel` for registry override tests.

        :param spec: Adapter or metric specification.

        :return: Configured mock chat model instance.
        """
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
        from backend.adapters.models.mocks import register_default_mocks

        register_default_mocks()


async def test_cancel_marks_run_cancelled_when_no_samples_succeed(
    in_memory_storage: SQLiteStorage,
    scripted_mock_chat: object,
) -> None:
    """
    Verify cancel marks run cancelled when no samples succeed.

    :param in_memory_storage: The in memory storage.
    :param scripted_mock_chat: The scripted mock chat.
    """
    engine = LocalEngine()
    await engine.cancel("run-local-4")
    result = await engine.run(_request("run-local-4"), in_memory_storage)
    await engine.close()
    assert result.status == "cancelled"
