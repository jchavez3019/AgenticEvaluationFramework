"""Behavioral tests for ``MockJudge``."""

from __future__ import annotations

import pytest

from aef.adapters.models.mocks import (
    MatchAny,
    MockChatModelError,
    MockJudge,
    MockJudgeScript,
)
from aef.contracts.adapter_spec import JudgeAdapterSpec
from aef.contracts.primitives import (
    CriterionScore,
    JudgmentRequest,
    Rubric,
    RubricCriterion,
    RubricScore,
)


def _rubric() -> Rubric:
    return Rubric(
        name="quality",
        version="1",
        criteria=[
            RubricCriterion(
                name="correct",
                description="answer is correct",
                scale="binary",
            ),
        ],
    )


def _spec() -> JudgeAdapterSpec:
    return JudgeAdapterSpec(
        name="mock-judge",
        model_id="mock-judge-id",
        judge_kind="single",
        rubric=_rubric(),
    )


def _request(candidate: str) -> JudgmentRequest:
    return JudgmentRequest(
        sample_idx=0,
        sample_input="What is 2+2?",
        candidate=candidate,
        rubric=_rubric(),
        rendered_prompt="judge prompt",
    )


@pytest.mark.asyncio
async def test_judge_returns_scripted_score() -> None:
    judge = MockJudge(
        _spec(),
        scripts=[
            MockJudgeScript(
                match=MatchAny(),
                score=RubricScore(
                    rubric_name="quality",
                    rubric_version="1",
                    criteria_scores=[
                        CriterionScore(
                            criterion="correct",
                            score=1.0,
                            rationale="matches reference",
                        ),
                    ],
                    overall=1.0,
                ),
            ),
        ],
    )

    response = await judge.judge(_request("4"))

    assert response.score.criteria_scores[0].score == 1.0
    assert response.score.overall == 1.0


@pytest.mark.asyncio
async def test_judge_no_match_raises() -> None:
    judge = MockJudge(_spec(), scripts=[])
    with pytest.raises(MockChatModelError):
        await judge.judge(_request("anything"))
