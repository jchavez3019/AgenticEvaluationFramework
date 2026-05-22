"""Round-trip and validator tests for ``backend.contracts.metric_result``."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.contracts.metric_result import (
    MetricApplicability,
    MetricInputs,
    MetricKind,
    MetricResult,
    MetricSpec,
    MetricStatus,
    SubScore,
)


def test_metric_kind_string_values() -> None:
    """Verify metric kind string values."""
    assert MetricKind.LEXICAL.value == "lexical"
    assert MetricKind.OPERATIONAL.value == "operational"


def test_metric_status_string_values() -> None:
    """Verify metric status string values."""
    assert MetricStatus.OK.value == "ok"
    assert MetricStatus.SKIPPED.value == "skipped"


def test_sub_score_round_trip() -> None:
    """Verify sub score round trip."""
    sub = SubScore(name="rouge_1_f1", value=0.62, notes="seeded")
    assert SubScore.model_validate(sub.model_dump()) == sub


def test_metric_spec_round_trip() -> None:
    """Verify metric spec round trip."""
    spec = MetricSpec(
        name="rouge",
        kind=MetricKind.LEXICAL,
        version="1.0",
        required_inputs=frozenset({"reference"}),
        applicable_when=MetricApplicability(requires_reference=True),
        config={"variants": "1,2,L"},
    )
    rebuilt = MetricSpec.model_validate(spec.model_dump())
    assert rebuilt == spec
    assert rebuilt.required_inputs == frozenset({"reference"})


def test_metric_inputs_round_trip() -> None:
    """Verify metric inputs round trip."""
    inputs = MetricInputs(
        sample_idx=3,
        input="What is the capital of France?",
        candidate="Paris.",
        reference="Paris",
    )
    assert MetricInputs.model_validate(inputs.model_dump()) == inputs


def test_metric_result_scalar_round_trip() -> None:
    """Verify metric result scalar round trip."""
    result = MetricResult(
        metric_name="bleu",
        metric_version="1.0",
        sample_idx=0,
        status=MetricStatus.OK,
        value=42.5,
        compute_latency_ms=1.2,
    )
    assert MetricResult.model_validate(result.model_dump()) == result


def test_metric_result_variadic_round_trip() -> None:
    """Verify metric result variadic round trip."""
    result = MetricResult(
        metric_name="rouge",
        metric_version="1.0",
        sample_idx=0,
        status=MetricStatus.OK,
        value=0.62,
        sub_values=[
            SubScore(name="rouge_1_f1", value=0.62),
            SubScore(name="rouge_2_f1", value=0.41),
        ],
    )
    assert MetricResult.model_validate(result.model_dump()) == result


def test_metric_result_skipped_no_value() -> None:
    """Verify metric result skipped no value."""
    result = MetricResult(
        metric_name="faithfulness",
        metric_version="1.0",
        sample_idx=0,
        status=MetricStatus.SKIPPED,
        value=None,
    )
    assert MetricResult.model_validate(result.model_dump()) == result


def test_metric_result_error_with_exception_fields() -> None:
    """Verify metric result error with exception fields."""
    result = MetricResult(
        metric_name="llm_judge",
        metric_version="llm_judge:1.0+prompt:v1",
        sample_idx=2,
        status=MetricStatus.ERROR,
        value=None,
        exception_class="JudgeOutputParseError",
        exception_message="Could not parse rubric JSON.",
    )
    rebuilt = MetricResult.model_validate(result.model_dump())
    assert rebuilt == result


def test_metric_spec_rejects_unknown_kind() -> None:
    """Verify metric spec rejects unknown kind."""
    with pytest.raises(ValidationError):
        MetricSpec.model_validate(
            {"name": "x", "kind": "perplexity", "version": "1.0"},
        )
