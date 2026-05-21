"""Behavioral tests for ``MockDatasetAdapter``."""

from __future__ import annotations

import pytest

from aef.adapters.datasets.mocks import MockDatasetAdapter
from aef.contracts.adapter_spec import DatasetAdapterSpec
from aef.contracts.primitives import EvaluationSample


def _spec() -> DatasetAdapterSpec:
    return DatasetAdapterSpec(name="mock", dataset_id="mock-id")


@pytest.mark.asyncio
async def test_default_dataset_yields_seeded_rows() -> None:
    async with MockDatasetAdapter(_spec()) as ds:
        rows = [row async for row in ds.load()]

    assert len(rows) == 5
    assert rows[0].input == "What is 1+1?"
    assert rows[0].reference == "2"
    assert rows[-1].input == "What is 5+5?"
    assert all(row.idx == i for i, row in enumerate(rows))


@pytest.mark.asyncio
async def test_explicit_rows_round_trip() -> None:
    rows = [
        EvaluationSample(idx=0, input="hi", reference="hello"),
        EvaluationSample(idx=1, input="bye", reference="goodbye"),
    ]

    async with MockDatasetAdapter(_spec(), rows=rows) as ds:
        materialized = [row async for row in ds.load()]

    assert materialized == rows


@pytest.mark.asyncio
async def test_dataset_run_is_repeatable() -> None:
    adapter = MockDatasetAdapter(_spec())
    async with adapter:
        first = [row async for row in adapter.load()]
    async with adapter:
        second = [row async for row in adapter.load()]

    assert first == second
