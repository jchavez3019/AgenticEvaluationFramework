"""Registry behavior — register / build / list / duplicate / unknown."""

from __future__ import annotations

import pytest

from backend.adapters import (
    DatasetAdapter,
    JudgeAdapter,
    ModelAdapter,
    build_dataset_adapter,
    build_judge_adapter,
    build_model_adapter,
    list_dataset_adapters,
    list_judge_adapters,
    list_model_adapters,
    register_model_adapter,
    unregister_model_adapter,
)
from backend.adapters.models.mocks import MockChatModel
from backend.contracts.adapter_spec import (
    DatasetAdapterSpec,
    JudgeAdapterSpec,
    ModelAdapterSpec,
)
from backend.contracts.primitives import (
    Rubric,
    RubricCriterion,
)


def _model_spec(name: str = "mock-chat") -> ModelAdapterSpec:
    """
    Model spec.

    :param name: The name.

    :return: A :class:`ModelAdapterSpec` instance.
    """
    return ModelAdapterSpec(name=name, model_id=f"{name}-id")


def _judge_spec(name: str = "mock-judge") -> JudgeAdapterSpec:
    """
    Judge spec.

    :param name: The name.

    :return: A :class:`JudgeAdapterSpec` instance.
    """
    return JudgeAdapterSpec(
        name=name,
        model_id=f"{name}-id",
        judge_kind="single",
        rubric=Rubric(
            name="quality",
            version="1",
            criteria=[
                RubricCriterion(
                    name="correct",
                    description="answer is correct",
                    scale="binary",
                ),
            ],
        ),
    )


def _dataset_spec(name: str = "mock") -> DatasetAdapterSpec:
    """
    Dataset spec.

    :param name: The name.

    :return: A :class:`DatasetAdapterSpec` instance.
    """
    return DatasetAdapterSpec(name=name, dataset_id=f"{name}-id")


def test_mock_adapters_registered_at_import() -> None:
    """Verify mock adapters registered at import."""
    assert "mock-chat" in list_model_adapters()
    assert "mock-judge" in list_judge_adapters()
    assert "mock" in list_dataset_adapters()


def test_build_returns_protocol_compliant_adapters() -> None:
    """Verify build returns protocol compliant adapters."""
    model = build_model_adapter(_model_spec())
    judge = build_judge_adapter(_judge_spec())
    dataset = build_dataset_adapter(_dataset_spec())

    assert isinstance(model, ModelAdapter)
    assert isinstance(judge, JudgeAdapter)
    assert isinstance(dataset, DatasetAdapter)
    assert model.spec.name == "mock-chat"
    assert judge.spec.name == "mock-judge"
    assert dataset.spec.name == "mock"


def test_build_unknown_raises_keyerror() -> None:
    """Verify build unknown raises keyerror."""
    with pytest.raises(KeyError, match="unknown adapter"):
        build_model_adapter(_model_spec(name="not-a-real-adapter"))


def test_register_duplicate_raises() -> None:
    """Verify register duplicate raises."""

    def _factory(spec: ModelAdapterSpec) -> ModelAdapter:
        """
        Construct a metric instance from ``spec``.

        :param spec: Adapter or metric specification.

        :return: A :class:`ModelAdapter` instance.
        """
        return MockChatModel(spec, scripts=[])

    register_model_adapter("dup-test-adapter", _factory)
    try:
        with pytest.raises(ValueError, match="already registered"):
            register_model_adapter("dup-test-adapter", _factory)
    finally:
        unregister_model_adapter("dup-test-adapter")
