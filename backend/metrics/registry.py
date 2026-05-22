"""Metric registry — name → factory, with entry-point discovery.

Mirrors :mod:`backend.adapters.registry` so contributors learn one shape.

# ADR: Default Metric Suite and Plugin Contract
# See: adr/0004-default-metric-suite-and-plugin-contract.md
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from importlib.metadata import entry_points
from typing import TYPE_CHECKING

from backend.contracts.metric_result import MetricSpec

if TYPE_CHECKING:
    from backend.metrics.base import Metric


_factories: dict[str, Callable[[MetricSpec], Metric]] = {}
_lock = threading.Lock()
_discovered = False
_ENTRY_POINT_GROUP = "backend.metrics"


def register_metric(
    name: str,
    factory: Callable[[MetricSpec], Metric],
) -> None:
    """
    Bind ``name`` to ``factory`` in the registry.

    Raises :class:`ValueError` on duplicate registration so silent overrides cannot creep in
    via re-imports.

    :param name: Metric name (must match ``spec.name`` at build time).
    :param factory: Callable ``(MetricSpec) -> Metric``.
    """
    with _lock:
        if name in _factories:
            raise ValueError(f"metric {name!r} is already registered")
        _factories[name] = factory


def unregister_metric(name: str) -> None:
    """
    Drop ``name`` from the registry; no-op if absent.

    :param name: Metric name to remove.
    """
    with _lock:
        _factories.pop(name, None)


def build_metric(spec: MetricSpec) -> Metric:
    """
    Resolve and construct the metric named by ``spec.name``.

    :param spec: :class:`MetricSpec` naming the implementation to construct.

    :return: :class:`Metric` instance.
    """
    with _lock:
        if spec.name not in _factories:
            _discover_entry_points_locked()
    if spec.name not in _factories:
        raise KeyError(
            f"unknown metric {spec.name!r} (known: {sorted(_factories)})",
        )
    return _factories[spec.name](spec)


def list_metrics() -> list[str]:
    """
    Sorted list of registered metric names (loads entry points lazily).

    :return: Sorted list of registered metric names.
    """
    with _lock:
        _discover_entry_points_locked()
        return sorted(_factories)


def _discover_entry_points_locked() -> None:
    """Load third-party metric factories from entry points (idempotent, locked)."""
    global _discovered  # — module-level discovery flag.
    if _discovered:
        return
    _discovered = True
    for ep in entry_points(group=_ENTRY_POINT_GROUP):
        if ep.name in _factories:
            continue
        _factories[ep.name] = ep.load()
