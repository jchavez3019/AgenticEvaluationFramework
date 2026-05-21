"""Model and judge adapter Protocols.

# ADR: Adapter Architecture for Models and Datasets
# See: adr/0003-adapter-architecture-for-models-and-datasets.md
# ADR: LLM-as-Judge Contract and Bias-Mitigation Defaults
# See: adr/0014-llm-as-judge-contract-and-bias-mitigation.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from aef.contracts.adapter_spec import JudgeAdapterSpec, ModelAdapterSpec
    from aef.contracts.primitives import (
        GenerationRequest,
        GenerationResponse,
        JudgmentRequest,
        JudgmentResponse,
    )


@runtime_checkable
class ModelAdapter(Protocol):
    """The contract every text-generation adapter satisfies.

    Concrete adapters expose ``spec`` as a Pydantic
    :class:`ModelAdapterSpec` and implement async :meth:`generate`.
    ``close`` is called once at run finalize so adapters that hold
    long-lived resources (loaded HF models, HTTP clients) can release
    them.

    ``spec`` is declared via a read-only property so a
    :class:`JudgeAdapter` Protocol can refine it to
    :class:`JudgeAdapterSpec` (Pyright treats class attributes as
    invariant; properties are covariant on read).
    """

    @property
    def spec(self) -> ModelAdapterSpec:
        """The adapter's typed configuration spec."""
        ...

    async def generate(
        self,
        request: GenerationRequest,
    ) -> GenerationResponse:
        """Produce a single :class:`GenerationResponse` for ``request``.

        :raises UnsupportedSamplingParameterError: when ``request.sampling``
            sets a parameter the adapter does not advertise.
        :raises ContextOverflowError: when the adapter can count tokens
            and the request exceeds its context window.
        """
        ...

    async def close(self) -> None:
        """Release resources held by the adapter (idempotent)."""
        ...


@runtime_checkable
class JudgeAdapter(ModelAdapter, Protocol):
    """A :class:`ModelAdapter` that also produces structured judgments.

    Inherits :meth:`generate` so engines can route a judge through the
    same generation path as a regular model when needed; the additional
    :meth:`judge` method takes a typed :class:`JudgmentRequest` and
    returns a :class:`JudgmentResponse` whose :attr:`score` is a
    :class:`RubricScore` (per ADR-0014 §1).
    """

    @property
    def spec(self) -> JudgeAdapterSpec:
        """The judge adapter's typed configuration spec."""
        ...

    async def judge(self, request: JudgmentRequest) -> JudgmentResponse:
        """Produce a structured rubric judgment for ``request``.

        Bias mitigations (position swap for pairwise judges, anchors,
        determinism) are applied by the metric layer using fields on
        :attr:`JudgmentRequest.bias_mitigation`.
        """
        ...
