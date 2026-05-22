"""Dataset adapter Protocol.

# ADR: Adapter Architecture for Models and Datasets
# See: adr/0003-adapter-architecture-for-models-and-datasets.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, Self, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from types import TracebackType

    from backend.contracts.adapter_spec import DatasetAdapterSpec
    from backend.contracts.primitives import EvaluationSample


@runtime_checkable
class DatasetAdapter(Protocol):
    """The contract every dataset adapter satisfies.

    Concrete adapters carry a :class:`DatasetAdapterSpec` on ``spec``,
    behave as an async context manager (so streaming sources can manage
    file / HTTP handles), and expose :meth:`load` as an async iterator
    of :class:`EvaluationSample` rows.
    """

    spec: DatasetAdapterSpec

    async def __aenter__(self) -> Self:
        """
        Enter the dataset adapter's async context.

        :return: :class:`Self` instance.
        """
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """
        Exit the dataset adapter's async context.

        :param exc_type: Exception type raised in the block, if any.
        :param exc: Exception instance raised in the block, if any.
        :param tb: Exception traceback object, if any.
        """
        ...

    def load(self) -> AsyncIterator[EvaluationSample]:
        """
        Stream :class:`EvaluationSample` rows.

        Implementations return an async iterator; callers consume it with ``async for sample in
        adapter.load(): ...``.

        :yields: One :class:`EvaluationSample` per iteration.
        """
        ...
