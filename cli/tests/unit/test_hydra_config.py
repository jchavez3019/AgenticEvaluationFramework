"""Unit tests for Hydra composition of evaluation-run configs."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from cli.config import register_configs
from cli.entrypoint import request_from_cfg
from hydra import compose, initialize_config_dir
from hydra.core.global_hydra import GlobalHydra

_CONFIG_DIR = str(Path(__file__).resolve().parents[3] / "configs")


@pytest.fixture(autouse=True)
def clear_hydra() -> Generator[None, None, None]:
    """
    Reset the global Hydra singleton before and after each test.

    :yields: Nothing; performs setup and teardown only.
    """
    GlobalHydra.instance().clear()
    yield
    GlobalHydra.instance().clear()


@pytest.fixture
def hydra_ctx() -> Generator[None, None, None]:
    """
    Register configs and initialize Hydra against the repo ``configs/`` tree.

    :yields: Nothing; provides an initialized Hydra context for the test body.
    """
    register_configs()
    with initialize_config_dir(
        config_dir=_CONFIG_DIR,
        version_base="1.3",
    ):
        yield


def test_compose_default_mock_run(hydra_ctx: None) -> None:
    """Default ``eval_run`` composition resolves to the mock adapter stack.

    :param hydra_ctx: Initialized Hydra config directory fixture.
    """
    cfg = compose(config_name="eval_run", overrides=[])
    request = request_from_cfg(cfg)
    assert request.model.name == "mock-chat"
    assert request.run_id not in ("", "PLACEHOLDER")
    assert len(request.metrics) == 3


def test_compose_override_seed(hydra_ctx: None) -> None:
    """CLI override ``seed=42`` is reflected in the composed request.

    :param hydra_ctx: Initialized Hydra config directory fixture.
    """
    cfg = compose(config_name="eval_run", overrides=["seed=42"])
    request = request_from_cfg(cfg)
    assert request.seed == 42


def test_compose_override_sampling_preset(hydra_ctx: None) -> None:
    """Selecting ``sampling=greedy`` applies the greedy preset.

    :param hydra_ctx: Initialized Hydra config directory fixture.
    """
    cfg = compose(config_name="eval_run", overrides=["sampling=greedy"])
    request = request_from_cfg(cfg)
    assert request.sampling.temperature == 0.0


def test_compose_override_sampling_field(hydra_ctx: None) -> None:
    """Field-level sampling overrides compose on top of a preset.

    :param hydra_ctx: Initialized Hydra config directory fixture.
    """
    cfg = compose(
        config_name="eval_run",
        overrides=["sampling=greedy", "sampling.temperature=0.25"],
    )
    request = request_from_cfg(cfg)
    assert request.sampling.temperature == 0.25
