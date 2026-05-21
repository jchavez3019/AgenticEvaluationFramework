"""Metric registry — name → factory, with entry-point discovery.

Mirrors :mod:`aef.adapters.registry` so contributors learn one shape.

# ADR: Default Metric Suite and Plugin Contract
# See: adr/0004-default-metric-suite-and-plugin-contract.md
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from aef.contracts.metric_result import MetricSpec

if TYPE_CHECKING:
    from aef.metrics.base import Metric


_factories: dict[str, Callable[[MetricSpec], Metric]] = {}
_lock = threading.Lock()
_discovered = False
_ENTRY_POINT_GROUP = "aef.metrics"


def register_metric(
    name: str,
    factory: Callable[[MetricSpec], Metric],
) -> None:
    """Bind ``name`` to ``factory`` in the registry.

    Raises :class:`ValueError` on duplicate registration so silent
    overrides cannot creep in via re-imports.
    """
    with _lock:
        if name in _factories:
            raise ValueError(f"metric {name!r} is already registered")
        _factories[name] = factory


def unregister_metric(name: str) -> None:
    """Drop ``name`` from the registry; no-op if absent."""
    with _lock:
        _factories.pop(name, None)


def build_metric(spec: MetricSpec) -> Metric:
    """Resolve and construct the metric named by ``spec.name``."""
    with _lock:
        if spec.name not in _factories:
            _discover_entry_points_locked()
    if spec.name not in _factories:
        raise KeyError(
            f"unknown metric {spec.name!r} (known: {sorted(_factories)})",
        )
    return _factories[spec.name](spec)


def list_metrics() -> list[str]:
    """Sorted list of registered metric names (loads entry points lazily)."""
    with _lock:
        _discover_entry_points_locked()
        return sorted(_factories)


def _discover_entry_points_locked() -> None:
    global _discovered  # — module-level discovery flag.
    if _discovered:
        return
    _discovered = True
    for ep in entry_points(group=_ENTRY_POINT_GROUP):
        if ep.name in _factories:
            continue
        _factories[ep.name] = ep.load()
