"""Round-trip and validator tests for ``aef.contracts.adapter_spec``."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aef.contracts.adapter_spec import (
    DatasetAdapterSpec,
    JudgeAdapterSpec,
    ModelAdapterSpec,
    ModelCapabilities,
)
from aef.contracts.primitives import Rubric, RubricCriterion


def _make_rubric() -> Rubric:
    return Rubric(
        name="default_v1",
        version="1.0",
        criteria=[
            RubricCriterion(
                name="factual_accuracy",
                description="Is the answer correct?",
                scale="likert_5",
            ),
            RubricCriterion(
                name="relevance",
                description="Is the answer relevant?",
                scale="likert_5",
            ),
        ],
    )


def test_model_capabilities_round_trip() -> None:
    caps = ModelCapabilities(
        supports_streaming=True,
        max_context_tokens=4096,
        requires_gpu=True,
        is_remote=False,
        cost_reporting="tokens-only",
        supported_sampling_parameters=frozenset({"temperature", "max_output_tokens"}),
        family="local-hf",
    )
    dumped = caps.model_dump()
    rebuilt = ModelCapabilities.model_validate(dumped)
    assert rebuilt == caps


def test_model_capabilities_max_context_tokens_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ModelCapabilities(max_context_tokens=0)


def test_model_adapter_spec_round_trip() -> None:
    spec = ModelAdapterSpec(
        name="huggingface",
        model_id="HuggingFaceTB/SmolLM2-135M-Instruct",
        description="Pinned smoke-test model.",
        capabilities=ModelCapabilities(
            max_context_tokens=2048,
            requires_gpu=True,
            family="local-hf",
            supported_sampling_parameters=frozenset({"temperature", "seed"}),
        ),
        config={"revision": "abc123"},
    )
    rebuilt = ModelAdapterSpec.model_validate(spec.model_dump())
    assert rebuilt == spec
    assert rebuilt.capabilities.supported_sampling_parameters == frozenset(
        {"temperature", "seed"},
    )


def test_dataset_adapter_spec_round_trip() -> None:
    spec = DatasetAdapterSpec(
        name="csv",
        dataset_id="./data/eval.csv",
        row_count=128,
        provides=frozenset({"reference"}),
    )
    rebuilt = DatasetAdapterSpec.model_validate(spec.model_dump())
    assert rebuilt == spec


def test_judge_adapter_spec_round_trip() -> None:
    spec = JudgeAdapterSpec(
        name="mock-judge",
        model_id="mock-judge-1",
        capabilities=ModelCapabilities(
            family="mock",
            supported_sampling_parameters=frozenset({"temperature", "seed"}),
        ),
        judge_kind="single",
        rubric=_make_rubric(),
    )
    rebuilt = JudgeAdapterSpec.model_validate(spec.model_dump())
    assert rebuilt == spec
    assert rebuilt.deterministic is True
    assert rebuilt.response_schema_name == "RubricScore"


def test_judge_adapter_spec_rejects_unknown_judge_kind() -> None:
    with pytest.raises(ValidationError):
        JudgeAdapterSpec(
            name="bad",
            model_id="m",
            judge_kind="rubric",  # type: ignore[arg-type]  # not in JudgeKind
            rubric=_make_rubric(),
        )


def test_specs_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ModelAdapterSpec.model_validate(
            {"name": "x", "model_id": "y", "extra_field": "boom"},
        )
    with pytest.raises(ValidationError):
        DatasetAdapterSpec.model_validate(
            {"name": "x", "dataset_id": "y", "extra_field": "boom"},
        )
