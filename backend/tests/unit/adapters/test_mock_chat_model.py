"""Behavioral tests for ``MockChatModel``."""

from __future__ import annotations

import asyncio
import time

import pytest

from aef.adapters.capabilities import UnsupportedSamplingParameterError
from aef.adapters.models.mocks import (
    MatchAny,
    MatchExactPrefix,
    MatchRegex,
    MockChatModel,
    MockChatModelError,
    MockChatScript,
)
from aef.contracts.adapter_spec import ModelAdapterSpec, ModelCapabilities
from aef.contracts.primitives import (
    ChatMessage,
    GenerationConfig,
    GenerationRequest,
    Usage,
)


def _spec(
    *,
    capabilities: ModelCapabilities | None = None,
) -> ModelAdapterSpec:
    return ModelAdapterSpec(
        name="mock-chat",
        model_id="mock-chat-id",
        capabilities=capabilities or ModelCapabilities(family="mock"),
    )


def _request(content: str) -> GenerationRequest:
    return GenerationRequest(messages=[ChatMessage(role="user", content=content)])


@pytest.mark.asyncio
async def test_first_matching_script_wins() -> None:
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
    model = MockChatModel(_spec(), scripts=[])
    await model.close()
    await model.close()


@pytest.mark.asyncio
async def test_concurrent_generate_is_safe() -> None:
    model = MockChatModel(
        _spec(),
        scripts=[MockChatScript(match=MatchAny(), response="ok")],
    )

    requests = [_request(f"q-{i}") for i in range(8)]
    responses = await asyncio.gather(*[model.generate(r) for r in requests])

    assert all(r.text == "ok" for r in responses)
