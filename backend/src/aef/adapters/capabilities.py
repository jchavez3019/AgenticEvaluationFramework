"""Capability validation — typed errors raised before any model call.

The two errors defined here are the framework's contract for "this
generation request cannot be honored": one when the user explicitly sets
a sampling parameter the adapter does not support, one when the prompt
plus requested completion would exceed the adapter's context window.

# ADR: Adapter Architecture for Models and Datasets
# See: adr/0003-adapter-architecture-for-models-and-datasets.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aef.contracts.adapter_spec import (
        ModelCapabilities,
        SamplingParameter,
    )
    from aef.contracts.primitives import GenerationConfig

_SAMPLING_FIELD_NAMES: tuple[str, ...] = (
    "temperature",
    "top_k",
    "top_p",
    "repetition_penalty",
    "max_output_tokens",
    "seed",
)


class UnsupportedSamplingParameterError(ValueError):
    """Raised when a request explicitly sets a parameter the adapter cannot honor.

    The check happens during request construction so the user sees the
    error before any side-effecting model call.
    """

    def __init__(
        self,
        adapter_name: str,
        unsupported: frozenset[SamplingParameter],
        supported: frozenset[SamplingParameter],
    ) -> None:
        """Compose a human-readable diagnostic message.

        :param adapter_name: ``ModelAdapterSpec.name`` for context.
        :param unsupported: parameters the request set that the adapter
            cannot honor.
        :param supported: parameters the adapter advertises.
        """
        self.adapter_name = adapter_name
        self.unsupported = unsupported
        self.supported = supported
        super().__init__(
            f"Adapter {adapter_name!r} does not support sampling "
            f"parameters: {sorted(unsupported)} (supported: {sorted(supported)})",
        )


class ContextOverflowError(ValueError):
    """Raised when ``prompt_tokens + max_output_tokens`` exceeds the model context.

    The validator is opt-in per adapter — adapters that cannot count
    their own tokens leave ``capabilities.max_context_tokens=None`` and
    skip the check.
    """

    def __init__(
        self,
        adapter_name: str,
        prompt_tokens: int,
        max_output_tokens: int,
        max_context_tokens: int,
    ) -> None:
        """Compose a human-readable diagnostic message."""
        self.adapter_name = adapter_name
        self.prompt_tokens = prompt_tokens
        self.max_output_tokens = max_output_tokens
        self.max_context_tokens = max_context_tokens
        super().__init__(
            f"Adapter {adapter_name!r}: prompt_tokens ({prompt_tokens}) "
            f"+ max_output_tokens ({max_output_tokens}) "
            f"= {prompt_tokens + max_output_tokens} "
            f"exceeds max_context_tokens ({max_context_tokens})",
        )


def validate_against_capabilities(
    *,
    adapter_name: str,
    capabilities: ModelCapabilities,
    sampling: GenerationConfig,
    prompt_tokens: int | None = None,
) -> None:
    """Validate a request against an adapter's declared capabilities.

    Two checks happen:

    1. Every sampling field the user explicitly set (i.e., not ``None``)
       must appear in :attr:`ModelCapabilities.supported_sampling_parameters`.
       Unsupported parameters raise :class:`UnsupportedSamplingParameterError`.
    2. When the adapter declares :attr:`ModelCapabilities.max_context_tokens`
       and ``prompt_tokens`` is supplied, the sum of ``prompt_tokens`` +
       ``sampling.max_output_tokens`` must not exceed the limit.
       Overflow raises :class:`ContextOverflowError`.

    :raises UnsupportedSamplingParameterError: see check 1.
    :raises ContextOverflowError: see check 2.
    """
    explicitly_set: set[SamplingParameter] = set()
    for field in _SAMPLING_FIELD_NAMES:
        if getattr(sampling, field) is not None:
            explicitly_set.add(field)  # type: ignore[arg-type]

    unsupported = frozenset(explicitly_set - capabilities.supported_sampling_parameters)
    if unsupported:
        raise UnsupportedSamplingParameterError(
            adapter_name=adapter_name,
            unsupported=unsupported,
            supported=capabilities.supported_sampling_parameters,
        )

    if (
        capabilities.max_context_tokens is not None
        and prompt_tokens is not None
        and sampling.max_output_tokens is not None
        and prompt_tokens + sampling.max_output_tokens > capabilities.max_context_tokens
    ):
        raise ContextOverflowError(
            adapter_name=adapter_name,
            prompt_tokens=prompt_tokens,
            max_output_tokens=sampling.max_output_tokens,
            max_context_tokens=capabilities.max_context_tokens,
        )
