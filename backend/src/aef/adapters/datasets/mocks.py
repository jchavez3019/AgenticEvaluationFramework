"""Deterministic mock dataset adapter.

Registers under ``"mock"``. The default factory produces a tiny
five-row dataset so the registry-backed engine path is exercised even
when a test doesn't supply explicit rows.

# ADR: Adapter Architecture for Models and Datasets
# See: adr/0003-adapter-architecture-for-models-and-datasets.md
# ADR: Testing Strategy and Mock Adapters
# See: adr/0011-testing-strategy-and-mock-adapters.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from aef.adapters.registry import register_dataset_adapter
from aef.contracts.adapter_spec import DatasetAdapterSpec
from aef.contracts.primitives import EvaluationSample

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from types import TracebackType


def _seeded_rows(count: int) -> list[EvaluationSample]:
    """Build deterministic rows for a tiny seeded dataset.

    The arithmetic answers are deliberately exact so lexical metrics
    (BLEU / exact-match) on a pass-through adapter produce
    well-understood reference values.
    """
    inputs = [
        ("What is 1+1?", "2"),
        ("What is 2+2?", "4"),
        ("What is 3+3?", "6"),
        ("What is 4+4?", "8"),
        ("What is 5+5?", "10"),
    ]
    rows: list[EvaluationSample] = []
    for idx in range(count):
        question, answer = inputs[idx % len(inputs)]
        rows.append(
            EvaluationSample(
                idx=idx,
                input=question,
                reference=answer,
            ),
        )
    return rows


class MockDatasetAdapter:
    """Deterministic in-memory dataset for tests.

    Construct directly with explicit ``rows`` for full control, or rely
    on the registry factory which builds a seeded five-row dataset.
    """

    def __init__(
        self,
        spec: DatasetAdapterSpec,
        *,
        rows: list[EvaluationSample] | None = None,
    ) -> None:
        """Hold the spec and the materialized row list."""
        self.spec = spec
        self._rows = rows if rows is not None else _seeded_rows(5)

    async def __aenter__(self) -> Self:
        """Enter the adapter's async context (no-op for the mock)."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Exit the adapter's async context (no-op for the mock)."""
        return None

    async def load(self) -> AsyncIterator[EvaluationSample]:
        """Yield each :class:`EvaluationSample` in order."""
        for row in self._rows:
            yield row


def _factory(spec: DatasetAdapterSpec) -> MockDatasetAdapter:
    """Build a default :class:`MockDatasetAdapter` from spec."""
    return MockDatasetAdapter(spec)


def _register() -> None:
    try:
        register_dataset_adapter("mock", _factory)
    except ValueError:
        pass


_register()


__all__ = ["MockDatasetAdapter"]
