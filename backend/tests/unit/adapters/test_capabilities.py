"""Capability-validation unit tests."""

from __future__ import annotations

import pytest

from backend.adapters.capabilities import (
    ContextOverflowError,
    UnsupportedSamplingParameterError,
    validate_against_capabilities,
)
from backend.contracts.adapter_spec import ModelCapabilities
from backend.contracts.primitives import GenerationConfig


def test_supported_parameter_passes_validation() -> None:
    """Verify supported parameter passes validation."""
    capabilities = ModelCapabilities(
        supported_sampling_parameters=frozenset({"temperature", "max_output_tokens"}),
    )
    sampling = GenerationConfig(temperature=0.5, max_output_tokens=64)

    validate_against_capabilities(
        adapter_name="test",
        capabilities=capabilities,
        sampling=sampling,
    )


def test_unsupported_parameter_raises() -> None:
    """Verify unsupported parameter raises."""
    capabilities = ModelCapabilities(
        supported_sampling_parameters=frozenset({"temperature"}),
    )
    sampling = GenerationConfig(temperature=0.5, top_p=0.9)

    with pytest.raises(UnsupportedSamplingParameterError) as exc:
        validate_against_capabilities(
            adapter_name="test",
            capabilities=capabilities,
            sampling=sampling,
        )

    assert exc.value.unsupported == frozenset({"top_p"})
    assert exc.value.adapter_name == "test"


def test_unset_parameter_does_not_raise_even_if_unsupported() -> None:
    """Verify unset parameter does not raise even if unsupported."""
    capabilities = ModelCapabilities(
        supported_sampling_parameters=frozenset({"temperature"}),
    )
    sampling = GenerationConfig()

    validate_against_capabilities(
        adapter_name="test",
        capabilities=capabilities,
        sampling=sampling,
    )


def test_context_overflow_raises_when_sum_exceeds_limit() -> None:
    """Verify context overflow raises when sum exceeds limit."""
    capabilities = ModelCapabilities(
        max_context_tokens=128,
        supported_sampling_parameters=frozenset({"max_output_tokens"}),
    )
    sampling = GenerationConfig(max_output_tokens=64)

    with pytest.raises(ContextOverflowError):
        validate_against_capabilities(
            adapter_name="test",
            capabilities=capabilities,
            sampling=sampling,
            prompt_tokens=100,
        )


def test_context_overflow_skipped_when_limit_unset() -> None:
    """Verify context overflow skipped when limit unset."""
    capabilities = ModelCapabilities(
        max_context_tokens=None,
        supported_sampling_parameters=frozenset({"max_output_tokens"}),
    )
    sampling = GenerationConfig(max_output_tokens=10_000)

    validate_against_capabilities(
        adapter_name="test",
        capabilities=capabilities,
        sampling=sampling,
        prompt_tokens=10_000,
    )


def test_context_overflow_skipped_when_prompt_tokens_unknown() -> None:
    """Verify context overflow skipped when prompt tokens unknown."""
    capabilities = ModelCapabilities(
        max_context_tokens=64,
        supported_sampling_parameters=frozenset({"max_output_tokens"}),
    )
    sampling = GenerationConfig(max_output_tokens=64)

    validate_against_capabilities(
        adapter_name="test",
        capabilities=capabilities,
        sampling=sampling,
        prompt_tokens=None,
    )
