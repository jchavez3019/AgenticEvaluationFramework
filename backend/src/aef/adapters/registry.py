"""Registries for model, judge, and dataset adapters.

Each registry maps a string identifier (the ``name`` field on the
adapter's spec) to a typed factory that constructs a concrete adapter
from the spec. Real adapters register themselves at module import; the
``aef.adapters`` package import triggers all of them.

Third-party packages can supply additional adapters via the
``aef.adapters.models``, ``aef.adapters.judges``, and
``aef.adapters.datasets`` Python entry-point groups (lazy discovery on
first lookup).

# ADR: Adapter Architecture for Models and Datasets
# See: adr/0003-adapter-architecture-for-models-and-datasets.md
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from aef.adapters.datasets.base import DatasetAdapter
    from aef.adapters.models.base import JudgeAdapter, ModelAdapter
    from aef.contracts.adapter_spec import (
        DatasetAdapterSpec,
        JudgeAdapterSpec,
        ModelAdapterSpec,
    )


SpecT = TypeVar("SpecT")
AdapterT = TypeVar("AdapterT")


class _Registry[SpecT, AdapterT]:
    """Tiny thread-safe registry keyed by adapter ``name``.

    Two layers compose:

    1. In-tree adapters call :meth:`register` from their module top.
    2. Third-party adapters publish to a Python entry-point group and
       are loaded lazily on first :meth:`build`.
    """

    def __init__(self, entry_point_group: str) -> None:
        """Initialize the registry with an empty in-tree map."""
        self._factories: dict[str, Callable[[SpecT], AdapterT]] = {}
        self._lock = threading.Lock()
        self._entry_point_group = entry_point_group
        self._discovered = False

    def register(
        self,
        name: str,
        factory: Callable[[SpecT], AdapterT],
    ) -> None:
        """Bind ``name`` to a factory, raising on duplicate keys."""
        with self._lock:
            if name in self._factories:
                raise ValueError(f"adapter {name!r} is already registered")
            self._factories[name] = factory

    def build(self, name: str, spec: SpecT) -> AdapterT:
        """Resolve ``name`` (loading entry points lazily) and call its factory."""
        with self._lock:
            if name not in self._factories:
                self._discover_entry_points_locked()
        if name not in self._factories:
            raise KeyError(
                f"unknown adapter {name!r} " f"(known: {sorted(self._factories)})",
            )
        return self._factories[name](spec)

    def names(self) -> list[str]:
        """Return the sorted list of currently registered adapter names."""
        with self._lock:
            self._discover_entry_points_locked()
            return sorted(self._factories)

    def unregister(self, name: str) -> None:
        """Drop ``name`` from the registry; no-op if it is not present.

        Exposed primarily so tests can clean up registrations they made
        for the duration of a test without leaking state across the
        rest of the suite.
        """
        with self._lock:
            self._factories.pop(name, None)

    def _discover_entry_points_locked(self) -> None:
        if self._discovered:
            return
        self._discovered = True
        for ep in entry_points(group=self._entry_point_group):
            if ep.name in self._factories:
                continue
            factory = ep.load()
            # Plugins must expose a callable that accepts the spec and
            # returns a concrete adapter; we trust the entry-point
            # contract because the registry boundary is the only seam
            # third-party code crosses.
            self._factories[ep.name] = factory


_MODEL_REGISTRY: _Registry[ModelAdapterSpec, ModelAdapter] = _Registry(
    "aef.adapters.models",
)
_JUDGE_REGISTRY: _Registry[JudgeAdapterSpec, JudgeAdapter] = _Registry(
    "aef.adapters.judges",
)
_DATASET_REGISTRY: _Registry[DatasetAdapterSpec, DatasetAdapter] = _Registry(
    "aef.adapters.datasets",
)


def register_model_adapter(
    name: str,
    factory: Callable[[ModelAdapterSpec], ModelAdapter],
) -> None:
    """Register a :class:`ModelAdapter` factory under ``name``."""
    _MODEL_REGISTRY.register(name, factory)


def register_judge_adapter(
    name: str,
    factory: Callable[[JudgeAdapterSpec], JudgeAdapter],
) -> None:
    """Register a :class:`JudgeAdapter` factory under ``name``."""
    _JUDGE_REGISTRY.register(name, factory)


def register_dataset_adapter(
    name: str,
    factory: Callable[[DatasetAdapterSpec], DatasetAdapter],
) -> None:
    """Register a :class:`DatasetAdapter` factory under ``name``."""
    _DATASET_REGISTRY.register(name, factory)


def build_model_adapter(spec: ModelAdapterSpec) -> ModelAdapter:
    """Resolve and instantiate the model adapter named by ``spec.name``."""
    return _MODEL_REGISTRY.build(spec.name, spec)


def build_judge_adapter(spec: JudgeAdapterSpec) -> JudgeAdapter:
    """Resolve and instantiate the judge adapter named by ``spec.name``."""
    return _JUDGE_REGISTRY.build(spec.name, spec)


def build_dataset_adapter(spec: DatasetAdapterSpec) -> DatasetAdapter:
    """Resolve and instantiate the dataset adapter named by ``spec.name``."""
    return _DATASET_REGISTRY.build(spec.name, spec)


def list_model_adapters() -> list[str]:
    """Return the sorted list of registered model-adapter names."""
    return _MODEL_REGISTRY.names()


def list_judge_adapters() -> list[str]:
    """Return the sorted list of registered judge-adapter names."""
    return _JUDGE_REGISTRY.names()


def list_dataset_adapters() -> list[str]:
    """Return the sorted list of registered dataset-adapter names."""
    return _DATASET_REGISTRY.names()


def unregister_model_adapter(name: str) -> None:
    """Drop ``name`` from the model-adapter registry."""
    _MODEL_REGISTRY.unregister(name)


def unregister_judge_adapter(name: str) -> None:
    """Drop ``name`` from the judge-adapter registry."""
    _JUDGE_REGISTRY.unregister(name)


def unregister_dataset_adapter(name: str) -> None:
    """Drop ``name`` from the dataset-adapter registry."""
    _DATASET_REGISTRY.unregister(name)
