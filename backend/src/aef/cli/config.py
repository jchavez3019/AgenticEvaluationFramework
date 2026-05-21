"""Hydra-zen config registration + typed instantiation.

``register_configs()`` populates hydra-zen's named store with every
config group ADR-0007 §1 commits to. Calling it is idempotent so the
CLI entry point and tests can both invoke it without coordination.

# ADR: CLI Configuration with Hydra and hydra-zen
# See: adr/0007-cli-configuration-with-hydra-and-hydra-zen.md
"""

from __future__ import annotations

import threading

from hydra_zen import builds, store

from aef.contracts.adapter_spec import (
    DatasetAdapterSpec,
    ModelAdapterSpec,
)
from aef.contracts.metric_result import MetricKind, MetricSpec
from aef.contracts.primitives import (
    EngineConfig,
    EvaluationSample,
    GenerationConfig,
    OutputConfig,
)
from aef.contracts.run import EvaluationRunRequest

_registered = False
_lock = threading.Lock()


def register_configs() -> None:
    """Populate hydra-zen's named store with every shipped config group."""
    global _registered  # — module-level init flag.
    with _lock:
        if _registered:
            return
        _registered = True

        _register_models()
        _register_datasets()
        _register_metrics()
        _register_engine()
        _register_sampling()
        _register_output()
        _register_top_level()


def _register_models() -> None:
    mock_chat = builds(
        ModelAdapterSpec,
        name="mock-chat",
        model_id="mock-chat",
        populate_full_signature=True,
        zen_partial=False,
    )
    store(mock_chat, group="model", name="mock")


def _register_datasets() -> None:
    mock_dataset = builds(
        DatasetAdapterSpec,
        name="mock",
        dataset_id="mock",
        populate_full_signature=True,
        zen_partial=False,
    )
    store(mock_dataset, group="dataset", name="mock")


def _register_metrics() -> None:
    """Register the ``metrics`` group as a list of :class:`MetricSpec`.

    Hydra config groups deal with single objects, so we register named
    presets that are each ``list[MetricSpec]`` literals. Selection is
    via ``metrics=lexical_only``.
    """
    exact = builds(
        MetricSpec,
        name="exact_match",
        kind=MetricKind.LEXICAL,
        populate_full_signature=True,
        zen_partial=False,
    )
    token_f1 = builds(
        MetricSpec,
        name="token_f1",
        kind=MetricKind.LEXICAL,
        populate_full_signature=True,
        zen_partial=False,
    )
    latency = builds(
        MetricSpec,
        name="latency",
        kind=MetricKind.OPERATIONAL,
        populate_full_signature=True,
        zen_partial=False,
    )
    store({"specs": [exact, token_f1, latency]}, group="metrics", name="default")
    store({"specs": [exact, token_f1]}, group="metrics", name="lexical_only")
    store({"specs": [latency]}, group="metrics", name="operational_only")


def _register_engine() -> None:
    local_engine = builds(
        EngineConfig,
        kind="local",
        populate_full_signature=True,
        zen_partial=False,
    )
    store(local_engine, group="engine", name="local")


def _register_sampling() -> None:
    default = builds(
        GenerationConfig,
        populate_full_signature=True,
        zen_partial=False,
    )
    greedy = builds(
        GenerationConfig,
        temperature=0.0,
        populate_full_signature=True,
        zen_partial=False,
    )
    balanced = builds(
        GenerationConfig,
        temperature=0.7,
        top_p=0.9,
        populate_full_signature=True,
        zen_partial=False,
    )
    creative = builds(
        GenerationConfig,
        temperature=1.0,
        top_p=0.95,
        repetition_penalty=1.1,
        populate_full_signature=True,
        zen_partial=False,
    )
    store(default, group="sampling", name="default")
    store(greedy, group="sampling", name="greedy")
    store(balanced, group="sampling", name="balanced")
    store(creative, group="sampling", name="creative")


def _register_output() -> None:
    default_output = builds(
        OutputConfig,
        populate_full_signature=True,
        zen_partial=False,
    )
    store(default_output, group="output", name="default")


def _register_top_level() -> None:
    """Top-level :class:`EvaluationRunRequest` config — composed from groups."""
    eval_run = builds(
        EvaluationRunRequest,
        run_id="${run_id}",
        seed="${seed}",
        model="${model}",
        dataset="${dataset}",
        metrics="${metrics.specs}",
        sampling="${sampling}",
        engine="${engine}",
        output="${output}",
        populate_full_signature=True,
        zen_partial=False,
    )
    store(eval_run, name="eval_run_config")


def build_run_id() -> str:
    """Generate a sortable run identifier (UUIDv7-like via ``uuid.uuid4``)."""
    import uuid

    return str(uuid.uuid4())


__all__ = ["EvaluationSample", "build_run_id", "register_configs"]
