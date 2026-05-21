"""Capability-validation unit tests."""

from __future__ import annotations

import pytest

from aef.adapters.capabilities import (
    ContextOverflowError,
    UnsupportedSamplingParameterError,
    validate_against_capabilities,
)
from aef.contracts.adapter_spec import ModelCapabilities
from aef.contracts.primitives import GenerationConfig


def test_supported_parameter_passes_validation() -> None:
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
