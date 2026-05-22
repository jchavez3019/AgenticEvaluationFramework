"""Round-trip and validator tests for ``backend.contracts.primitives``."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.contracts.primitives import (
    BiasMitigation,
    ChatMessage,
    EngineConfig,
    EvaluationSample,
    GenerationConfig,
    GenerationRequest,
    GenerationResponse,
    JudgmentRequest,
    JudgmentResponse,
    OutputConfig,
    PairwisePreference,
    RetrievedChunk,
    Rubric,
    RubricCriterion,
    RubricScore,
    SampleMetadata,
    Usage,
)


def _make_rubric() -> Rubric:
    """
    Make rubric.

    :return: A :class:`Rubric` instance.
    """
    return Rubric(
        name="default_v1",
        version="1.0",
        criteria=[
            RubricCriterion(
                name="factual_accuracy",
                description="Is the answer correct?",
                scale="likert_5",
            ),
        ],
    )


def test_chat_message_round_trip() -> None:
    """Verify chat message round trip."""
    msg = ChatMessage(role="user", content="hello", name="alice")
    assert ChatMessage.model_validate(msg.model_dump()) == msg


def test_generation_config_validators_clamp_temperature_high() -> None:
    """Verify generation config validators clamp temperature high."""
    with pytest.raises(ValidationError):
        GenerationConfig(temperature=2.5)


def test_generation_config_validators_clamp_temperature_low() -> None:
    """Verify generation config validators clamp temperature low."""
    with pytest.raises(ValidationError):
        GenerationConfig(temperature=-0.1)


def test_generation_config_validators_top_k_must_be_positive() -> None:
    """Verify generation config validators top k must be positive."""
    with pytest.raises(ValidationError):
        GenerationConfig(top_k=0)


def test_generation_config_validators_top_p_open_lower_bound() -> None:
    """Verify generation config validators top p open lower bound."""
    with pytest.raises(ValidationError):
        GenerationConfig(top_p=0.0)


def test_generation_config_round_trip_with_all_fields() -> None:
    """Verify generation config round trip with all fields."""
    cfg = GenerationConfig(
        temperature=0.7,
        top_k=40,
        top_p=0.95,
        repetition_penalty=1.05,
        max_output_tokens=128,
        seed=7,
    )
    assert GenerationConfig.model_validate(cfg.model_dump()) == cfg


def test_generation_response_round_trip() -> None:
    """Verify generation response round trip."""
    resp = GenerationResponse(
        text="hello world",
        finish_reason="stop",
        usage=Usage(prompt_tokens=4, completion_tokens=2, total_tokens=6),
        latency_ms=12.5,
    )
    assert GenerationResponse.model_validate(resp.model_dump()) == resp


def test_generation_request_requires_messages() -> None:
    """Verify generation request requires messages."""
    with pytest.raises(ValidationError):
        GenerationRequest(messages=[])


def test_evaluation_sample_round_trip_with_rag_context() -> None:
    """Verify evaluation sample round trip with rag context."""
    sample = EvaluationSample(
        idx=0,
        input="What is 2+2?",
        reference="4",
        context=[RetrievedChunk(text="2+2=4", chunk_id="c1", score=0.9)],
        metadata=SampleMetadata(
            dataset_split="test",
            difficulty="easy",
            tags=["math"],
        ),
    )
    assert EvaluationSample.model_validate(sample.model_dump()) == sample


def test_rubric_weighted_mean_requires_weights() -> None:
    """Verify rubric weighted mean requires weights."""
    with pytest.raises(ValidationError):
        Rubric(
            name="bad",
            version="1.0",
            criteria=[
                RubricCriterion(name="a", description="a", scale="likert_5"),
                RubricCriterion(name="b", description="b", scale="likert_5"),
            ],
            aggregation="weighted_mean",
        )


def test_rubric_weighted_mean_requires_matching_weight_count() -> None:
    """Verify rubric weighted mean requires matching weight count."""
    with pytest.raises(ValidationError):
        Rubric(
            name="bad",
            version="1.0",
            criteria=[
                RubricCriterion(name="a", description="a", scale="likert_5"),
                RubricCriterion(name="b", description="b", scale="likert_5"),
            ],
            aggregation="weighted_mean",
            weights=[1.0],
        )


def test_rubric_weighted_mean_with_matching_weights() -> None:
    """Verify rubric weighted mean with matching weights."""
    rubric = Rubric(
        name="ok",
        version="1.0",
        criteria=[
            RubricCriterion(name="a", description="a", scale="likert_5"),
            RubricCriterion(name="b", description="b", scale="likert_5"),
        ],
        aggregation="weighted_mean",
        weights=[0.7, 0.3],
    )
    assert Rubric.model_validate(rubric.model_dump()) == rubric


def test_bias_mitigation_defaults_are_all_on() -> None:
    """Verify bias mitigation defaults are all on."""
    bm = BiasMitigation()
    assert bm.position_swap is True
    assert bm.length_anchor is True
    assert bm.style_anchor is True
    assert bm.self_preference_warning is True
    assert bm.deterministic is True
    assert bm.require_rationale is True
    assert bm.parser_retries == 2


def test_pairwise_preference_round_trip() -> None:
    """Verify pairwise preference round trip."""
    score = RubricScore(
        rubric_name="default_v1",
        rubric_version="1.0",
        criteria_scores=[],
        overall=4.0,
    )
    pref = PairwisePreference(winner="A", confidence=0.8, score_a=score, score_b=score)
    assert PairwisePreference.model_validate(pref.model_dump()) == pref


def test_judgment_request_response_round_trip() -> None:
    """Verify judgment request response round trip."""
    rubric = _make_rubric()
    req = JudgmentRequest(
        sample_idx=0,
        sample_input="What is 2+2?",
        candidate="4",
        rubric=rubric,
        rendered_prompt="<rendered prompt>",
    )
    assert JudgmentRequest.model_validate(req.model_dump()) == req

    resp = JudgmentResponse(
        score=RubricScore(
            rubric_name=rubric.name,
            rubric_version=rubric.version,
            criteria_scores=[],
        ),
    )
    assert JudgmentResponse.model_validate(resp.model_dump()) == resp


def test_engine_config_defaults_are_local() -> None:
    """Verify engine config defaults are local."""
    cfg = EngineConfig()
    assert cfg.kind == "local"
    assert cfg.queues["generation"].pool_size == 1
    assert cfg.queues["scoring_judge"].pool_size == 0


def test_output_config_defaults() -> None:
    """Verify output config defaults."""
    out = OutputConfig()
    assert out.base_dir == "outputs"
    assert out.write_result_json is True
    assert out.write_run_log is True
