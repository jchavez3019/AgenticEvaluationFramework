"""``GET /metrics`` — registered metric implementations.

# ADR: Backend Technology Stack
# See: adr/0002-backend-technology-stack.md
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.schemas import AdapterListItem, AdapterListResponse
from backend.metrics.registry import list_metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", response_model=AdapterListResponse)
async def get_metrics() -> AdapterListResponse:
    """
    List every registered metric, by name.

    :return: :class:`AdapterListResponse` instance.
    """
    return AdapterListResponse(
        items=[AdapterListItem(name=name, kind="metric") for name in list_metrics()],
    )
