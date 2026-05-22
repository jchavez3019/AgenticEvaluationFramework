"""Behavioral tests for ``MockChatModel``."""

from __future__ import annotations

import asyncio
import time

import pytest

from backend.adapters.capabilities import UnsupportedSamplingParameterError
from backend.adapters.models.mocks import (
    MatchAny,
    MatchExactPrefix,
    MatchRegex,
    MockChatModel,
    MockChatModelError,
    MockChatScript,
)
from backend.contracts.adapter_spec import ModelAdapterSpec, ModelCapabilities
from backend.contracts.primitives import (
    ChatMessage,
    GenerationConfig,
    GenerationRequest,
    Usage,
)


def _spec(
    *,
    capabilities: ModelCapabilities | None = None,
) -> ModelAdapterSpec:
    """
    Spec.

    :param capabilities: The capabilities.

    :return: A :class:`ModelAdapterSpec` instance.
    """
    return ModelAdapterSpec(
        name="mock-chat",
        model_id="mock-chat-id",
        capabilities=capabilities or ModelCapabilities(family="mock"),
    )


def _request(content: str) -> GenerationRequest:
    """
    Request.

    :param content: The content.

    :return: A :class:`GenerationRequest` instance.
    """
    return GenerationRequest(messages=[ChatMessage(role="user", content=content)])


@pytest.mark.asyncio
async def test_first_matching_script_wins() -> None:
    """Verify first matching script wins."""
    model = MockChatModel(
        _spec(),
        scripts=[
            MockChatScript(
                match=MatchExactPrefix(prefix="What is 1+1"),
                response="2",
            ),
            MockChatScript(
                match=MatchAny(),
                response="<fallthrough>",
            ),
        ],
    )

    response = await model.generate(_request("What is 1+1?"))

    assert response.text == "2"
    assert response.finish_reason == "stop"


@pytest.mark.asyncio
async def test_regex_match_works() -> None:
    """Verify regex match works."""
    model = MockChatModel(
        _spec(),
        scripts=[
            MockChatScript(
                match=MatchRegex(pattern=r"\d+\s*\+\s*\d+"),
                response="<arithmetic>",
            ),
        ],
    )

    response = await model.generate(_request("Compute 7 + 8 please"))

    assert response.text == "<arithmetic>"


@pytest.mark.asyncio
async def test_no_match_raises_mock_chat_model_error() -> None:
    """Verify no match raises mock chat model error."""
    model = MockChatModel(
        _spec(),
        scripts=[
            MockChatScript(
                match=MatchExactPrefix(prefix="hello"),
                response="hi",
            ),
        ],
    )

    with pytest.raises(MockChatModelError):
        await model.generate(_request("not a hello"))


@pytest.mark.asyncio
async def test_unsupported_sampling_parameter_raises() -> None:
    """Verify unsupported sampling parameter raises."""
    capabilities = ModelCapabilities(
        family="mock",
        supported_sampling_parameters=frozenset({"temperature"}),
    )
    model = MockChatModel(
        _spec(capabilities=capabilities),
        scripts=[MockChatScript(match=MatchAny(), response="ok")],
    )

    request = GenerationRequest(
        messages=[ChatMessage(role="user", content="hi")],
        sampling=GenerationConfig(top_p=0.9),
    )

    with pytest.raises(UnsupportedSamplingParameterError):
        await model.generate(request)


@pytest.mark.asyncio
async def test_fail_with_raises_chosen_class() -> None:
    """Verify fail with raises chosen class."""
    model = MockChatModel(
        _spec(),
        scripts=[
            MockChatScript(
                match=MatchAny(),
                response="will fail",
                fail_with="TimeoutError",
            ),
        ],
    )

    with pytest.raises(TimeoutError):
        await model.generate(_request("anything"))


@pytest.mark.asyncio
async def test_latency_is_returned_on_response() -> None:
    """Verify latency is returned on response."""
    model = MockChatModel(
        _spec(),
        scripts=[
            MockChatScript(
                match=MatchAny(),
                response="hi",
                latency_ms=15.0,
                usage=Usage(prompt_tokens=4, completion_tokens=1, total_tokens=5),
            ),
        ],
        sleep_for_latency=False,
    )

    response = await model.generate(_request("ping"))

    assert response.latency_ms == 15.0
    assert response.usage.total_tokens == 5


@pytest.mark.asyncio
async def test_sleep_for_latency_actually_sleeps() -> None:
    """Verify sleep for latency actually sleeps."""
    model = MockChatModel(
        _spec(),
        scripts=[
            MockChatScript(match=MatchAny(), response="hi", latency_ms=20.0),
        ],
        sleep_for_latency=True,
    )

    start = time.perf_counter()
    await model.generate(_request("ping"))
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert elapsed_ms >= 15.0


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    """Verify close is idempotent."""
    model = MockChatModel(_spec(), scripts=[])
    await model.close()
    await model.close()


@pytest.mark.asyncio
async def test_concurrent_generate_is_safe() -> None:
    """Verify concurrent generate is safe."""
    model = MockChatModel(
        _spec(),
        scripts=[MockChatScript(match=MatchAny(), response="ok")],
    )

    requests = [_request(f"q-{i}") for i in range(8)]
    responses = await asyncio.gather(*[model.generate(r) for r in requests])

    assert all(r.text == "ok" for r in responses)
