"""Deterministic mock model and judge adapters.

The mocks register themselves at module import (under ``"mock-chat"``
and ``"mock-judge"``) so test code constructs them through the same
registry path real adapters use. There is no "test mode" branch in
production code.

# ADR: Adapter Architecture for Models and Datasets
# See: adr/0003-adapter-architecture-for-models-and-datasets.md
# ADR: Testing Strategy and Mock Adapters
# See: adr/0011-testing-strategy-and-mock-adapters.md
# ADR: LLM-as-Judge Contract and Bias-Mitigation Defaults
# See: adr/0014-llm-as-judge-contract-and-bias-mitigation.md
"""

from __future__ import annotations

import asyncio
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.adapters.capabilities import validate_against_capabilities
from backend.adapters.registry import register_judge_adapter, register_model_adapter
from backend.contracts.adapter_spec import JudgeAdapterSpec, ModelAdapterSpec
from backend.contracts.primitives import (
    GenerationRequest,
    GenerationResponse,
    JudgmentRequest,
    JudgmentResponse,
    RubricScore,
    Usage,
)
from backend.observability import get_logger

logger = get_logger(__name__)


class MockChatModelError(RuntimeError):
    """Raised when ``MockChatModel`` receives an unmatched request.

    Tests must declare the full set of expected requests up-front; a
    silent fallthrough would mask drift between the test fixture and the
    code under test.
    """


# ---------------------------------------------------------------------------
# Match rules — tagged union (per ADR-0011 §3).
# ---------------------------------------------------------------------------


class MatchExactPrefix(BaseModel):
    """Match when the last user-message content starts with ``prefix``.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * kind: Discriminator tag for the :data:`MockMatch` union.
    * prefix: Required leading substring on the last user message.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["exact_prefix"] = "exact_prefix"
    prefix: str = Field(min_length=1)


class MatchRegex(BaseModel):
    """Match when the last user-message content matches ``pattern``.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * kind: Discriminator tag for the :data:`MockMatch` union.
    * pattern: Regular expression matched against the last user message.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["regex"] = "regex"
    pattern: str = Field(min_length=1)


class MatchAny(BaseModel):
    """Match every request (typically used as a final fall-through).

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * kind: Discriminator tag for the :data:`MockMatch` union.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["any"] = "any"


MockMatch = MatchExactPrefix | MatchRegex | MatchAny


# ---------------------------------------------------------------------------
# MockChatModel
# ---------------------------------------------------------------------------


class MockChatScript(BaseModel):
    """One mapping rule from a request shape to a canned response.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * match: Rule selecting which requests this script handles.
    * response: Canned text returned when the rule matches.
    * latency_ms: Artificial latency applied before returning the response.
    * fail_with: Exception class name to raise instead of returning (when set).
    * usage: Token and cost accounting attached to the canned response.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    match: MockMatch = Field(discriminator="kind")
    response: str
    latency_ms: Annotated[float, Field(ge=0.0)] = 0.0
    fail_with: str | None = None
    usage: Usage = Field(default_factory=Usage)


class MockChatModel:
    """Deterministic chat model — first matching script wins.

    Satisfies the :class:`ModelAdapter` protocol and is registered as
    ``"mock-chat"``. See :meth:`__init__` for construction options.
    """

    def __init__(
        self,
        spec: ModelAdapterSpec,
        *,
        scripts: list[MockChatScript],
        seed: int = 0,
        sleep_for_latency: bool = True,
    ) -> None:
        """Configure scripts and latency behavior for :meth:`generate`.

        :param spec: Model adapter spec (capabilities drive validation).
        :param scripts: Ordered :class:`MockChatScript` rules; first match wins.
        :param seed: Reserved for future randomized scripts (unused today).
        :param sleep_for_latency: When ``True``, honor each script's ``latency_ms``.
        """
        self.spec = spec
        self._scripts = scripts
        self._seed = seed
        self._sleep_for_latency = sleep_for_latency

    async def generate(
        self,
        request: GenerationRequest,
    ) -> GenerationResponse:
        """Produce the canned response for the first matching script.

        :param request: Chat completion request (messages + sampling).

        :return: Canned :class:`GenerationResponse` from the first matching script.
        """
        validate_against_capabilities(
            adapter_name=self.spec.name,
            capabilities=self.spec.capabilities,
            sampling=request.sampling,
        )
        script = self._match(request)
        if script.fail_with is not None:
            raise _build_failure(script.fail_with, script.response)
        if script.latency_ms > 0 and self._sleep_for_latency:
            await asyncio.sleep(script.latency_ms / 1000.0)
        return GenerationResponse(
            text=script.response,
            finish_reason="stop",
            usage=script.usage,
            latency_ms=script.latency_ms,
        )

    async def close(self) -> None:
        """Mock adapter releases nothing — kept for Protocol conformance."""
        return None

    def _match(self, request: GenerationRequest) -> MockChatScript:
        """Select the first script whose rule matches the last user message.

        :param request: Generation request whose messages are inspected.

        :return: Matching :class:`MockChatScript`.

        :raises MockChatModelError: when no script matches.
        """
        last_user_content = _last_user_content(request)
        for script in self._scripts:
            if _match(script.match, last_user_content):
                return script
        raise MockChatModelError(
            f"MockChatModel({self.spec.name!r}): no script matched "
            f"last-user content {last_user_content!r}",
        )


# ---------------------------------------------------------------------------
# MockJudge
# ---------------------------------------------------------------------------


class MockJudgeScript(BaseModel):
    """Map a (input, candidate) tuple to a structured rubric score.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * match: Rule selecting which candidate texts this script handles.
    * score: Canned :class:`RubricScore` returned when the rule matches.
    * latency_ms: Artificial latency applied before returning the score.
    * fail_with: Exception class name to raise instead of returning (when set).
    * usage: Token and cost accounting attached to the judge call.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    match: MockMatch = Field(discriminator="kind")
    score: RubricScore
    latency_ms: Annotated[float, Field(ge=0.0)] = 0.0
    fail_with: str | None = None
    usage: Usage = Field(default_factory=Usage)


class MockJudge:
    """Deterministic LLM-as-judge mock.

    Matches against the candidate text. Tests script the rubric outputs
    they want to see; production-style judge metrics and bias-mitigation
    defaults consume the responses identically to real judges.
    """

    def __init__(
        self,
        spec: JudgeAdapterSpec,
        *,
        scripts: list[MockJudgeScript],
        seed: int = 0,
        sleep_for_latency: bool = True,
    ) -> None:
        """
        Hold the spec / scripts / seed for later :meth:`judge` calls.

        :param spec: Adapter or metric specification.
        :param scripts: Deterministic response scripts for the mock adapter.
        :param seed: Random seed for reproducible mock behavior.
        :param sleep_for_latency: Whether mock adapters simulate latency with ``asyncio.sleep``.
        """
        self.spec = spec
        self._scripts = scripts
        self._seed = seed
        self._sleep_for_latency = sleep_for_latency

    async def generate(
        self,
        request: GenerationRequest,
    ) -> GenerationResponse:
        """
        Generate a stub response so the Protocol is satisfied.

        The judge metric layer calls :meth:`judge`; this method exists only because
        :class:`JudgeAdapter` extends :class:`ModelAdapter`.

        :param request: Chat completion request (protocol stub; judges use :meth:`judge`).

        :return: Placeholder :class:`GenerationResponse` for protocol compliance.
        """
        validate_against_capabilities(
            adapter_name=self.spec.name,
            capabilities=self.spec.capabilities,
            sampling=request.sampling,
        )
        return GenerationResponse(
            text="<mock-judge-generate>",
            finish_reason="stop",
        )

    async def judge(self, request: JudgmentRequest) -> JudgmentResponse:
        """
        Return the structured judgment for the first matching script.

        :param request: Judgment request (candidate text + rubric context).

        :return: Structured :class:`JudgmentResponse` from the first matching script.
        """
        for script in self._scripts:
            if _match(script.match, request.candidate):
                if script.fail_with is not None:
                    raise _build_failure(script.fail_with, "judge failed")
                if script.latency_ms > 0 and self._sleep_for_latency:
                    await asyncio.sleep(script.latency_ms / 1000.0)
                return JudgmentResponse(
                    score=script.score,
                    usage=script.usage,
                    latency_ms=script.latency_ms,
                )
        raise MockChatModelError(
            f"MockJudge({self.spec.name!r}): no script matched " f"candidate {request.candidate!r}",
        )

    async def close(self) -> None:
        """Mock adapter releases nothing — kept for Protocol conformance."""
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _last_user_content(request: GenerationRequest) -> str:
    """Return text used for script matching from ``request.messages``.

    Prefers the last message with role ``user``; otherwise uses the final
    message in the list.

    :param request: Generation request whose messages are scanned.

    :return: User message content for rule evaluation.
    """
    for msg in reversed(request.messages):
        if msg.role == "user":
            return msg.content
    return request.messages[-1].content if request.messages else ""


def _match(rule: MockMatch, content: str) -> bool:
    """Evaluate whether ``content`` satisfies ``rule``.

    :param rule: Mock match rule (prefix, regex, or any).
    :param content: Candidate text (typically the last user message).

    :return: ``True`` when the rule matches.
    """
    if rule.kind == "any":
        return True
    if rule.kind == "exact_prefix":
        return content.startswith(rule.prefix)
    if rule.kind == "regex":
        return re.search(rule.pattern, content) is not None
    return False


_KNOWN_FAILURES: dict[str, type[BaseException]] = {
    "MockChatModelError": MockChatModelError,
    "RuntimeError": RuntimeError,
    "ValueError": ValueError,
    "TimeoutError": TimeoutError,
}


def _build_failure(class_name: str, message: str) -> BaseException:
    """Instantiate a known exception type for scripted failures.

    :param class_name: Key in :data:`_KNOWN_FAILURES` (falls back to ``RuntimeError``).
    :param message: Exception message text.

    :return: Exception instance to raise from :meth:`MockChatModel.generate`.
    """
    cls = _KNOWN_FAILURES.get(class_name, RuntimeError)
    return cls(message)


# ---------------------------------------------------------------------------
# Registry plumbing
# ---------------------------------------------------------------------------


def _build_default_chat_scripts() -> list[MockChatScript]:
    """
    Reasonable default script for ad-hoc constructions.

    The factory stores empty scripts; tests pass custom scripts through a wrapper because
    the registry receives only the spec.


    :return: :class:`MockChatScript` instance.
    """
    return [MockChatScript(match=MatchAny(), response="<mock>")]


def _model_factory(spec: ModelAdapterSpec) -> MockChatModel:
    """
    Construct a :class:`MockChatModel` from spec.

    The default scripts are intentionally minimal — tests build a :class:`MockChatModel`
    directly when they need scripted behavior.

    :param spec: Adapter or metric specification.

    :return: :class:`MockChatModel` instance.
    """
    return MockChatModel(spec, scripts=_build_default_chat_scripts())


def _judge_factory(spec: JudgeAdapterSpec) -> MockJudge:
    """
    Construct a :class:`MockJudge` with no scripts (tests supply them).

    :param spec: Adapter or metric specification.

    :return: :class:`MockJudge` instance.
    """
    return MockJudge(spec, scripts=[])


def register_default_mocks() -> None:
    """Register both mocks, but only once even on accidental re-import."""
    try:
        register_model_adapter("mock-chat", _model_factory)
    except ValueError:
        # Already registered — happens when this module is reloaded
        # inside a test session.
        pass
    try:
        register_judge_adapter("mock-judge", _judge_factory)
    except ValueError:
        pass


register_default_mocks()


__all__ = [
    "MatchAny",
    "MatchExactPrefix",
    "MatchRegex",
    "MockChatModel",
    "MockChatModelError",
    "MockChatScript",
    "MockJudge",
    "MockJudgeScript",
    "MockMatch",
    "register_default_mocks",
]
