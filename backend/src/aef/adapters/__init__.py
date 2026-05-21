"""Adapter framework — Protocols, registry, and shipped adapters.

Importing this package fires the registration of every shipped adapter so
``build_model_adapter("mock-chat", spec)`` works without any further
imports.

# ADR: Adapter Architecture for Models and Datasets
# See: adr/0003-adapter-architecture-for-models-and-datasets.md
"""

from __future__ import annotations

from aef.adapters.capabilities import (
    ContextOverflowError,
    UnsupportedSamplingParameterError,
    validate_against_capabilities,
)
from aef.adapters.datasets import mocks as _dataset_mocks
from aef.adapters.datasets.base import DatasetAdapter
from aef.adapters.models import mocks as _model_mocks
from aef.adapters.models.base import JudgeAdapter, ModelAdapter
from aef.adapters.registry import (
    build_dataset_adapter,
    build_judge_adapter,
    build_model_adapter,
    list_dataset_adapters,
    list_judge_adapters,
    list_model_adapters,
    register_dataset_adapter,
    register_judge_adapter,
    register_model_adapter,
    unregister_dataset_adapter,
    unregister_judge_adapter,
    unregister_model_adapter,
)

# Importing the mock submodules registers the adapters at package
# import time. Real adapters land in later milestones; their imports
# are lazy so optional groups (``transformers`` etc.) stay optional.
# Bound to a tuple so static checkers see the imports as used.
_REGISTERED_VIA_IMPORT = (_dataset_mocks, _model_mocks)

__all__ = [
    "ContextOverflowError",
    "DatasetAdapter",
    "JudgeAdapter",
    "ModelAdapter",
    "UnsupportedSamplingParameterError",
    "build_dataset_adapter",
    "build_judge_adapter",
    "build_model_adapter",
    "list_dataset_adapters",
    "list_judge_adapters",
    "list_model_adapters",
    "register_dataset_adapter",
    "register_judge_adapter",
    "register_model_adapter",
    "unregister_dataset_adapter",
    "unregister_judge_adapter",
    "unregister_model_adapter",
    "validate_against_capabilities",
]
