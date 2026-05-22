"""HTTP request / response Pydantic models.

The contracts module already defines the substantive shapes
(:class:`EvaluationRunRequest`, :class:`EvaluationRunResult`, etc.).
This module composes thin wrappers when the API needs paging,
listing, or status-only views.

# ADR: Backend Technology Stack
# See: adr/0002-backend-technology-stack.md
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from backend.contracts.persistence import RunListPage, RunQuery
from backend.contracts.run import EvaluationRunRequest, EvaluationRunResult


class CreateRunResponse(BaseModel):
    """Returned by ``POST /runs`` — the run identifier the caller can poll."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)


class AdapterListItem(BaseModel):
    """One entry in the registered-adapters listing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    kind: Annotated[str, Field(min_length=1)]


class AdapterListResponse(BaseModel):
    """Top-level body of ``GET /adapters``, ``/datasets``, ``/metrics``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[AdapterListItem]


__all__ = [
    "AdapterListItem",
    "AdapterListResponse",
    "CreateRunResponse",
    "EvaluationRunRequest",
    "EvaluationRunResult",
    "RunListPage",
    "RunQuery",
]
