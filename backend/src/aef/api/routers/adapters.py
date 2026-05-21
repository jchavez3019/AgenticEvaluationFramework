"""``GET /adapters`` — registered model adapters.

# ADR: Backend Technology Stack
# See: adr/0002-backend-technology-stack.md
"""

from __future__ import annotations

from fastapi import APIRouter

from aef.adapters.registry import list_judge_adapters, list_model_adapters
from aef.api.schemas import AdapterListItem, AdapterListResponse

router = APIRouter(prefix="/adapters", tags=["adapters"])


@router.get("", response_model=AdapterListResponse)
async def get_adapters() -> AdapterListResponse:
    """List every registered model and judge adapter, by name."""
    items: list[AdapterListItem] = []
    for name in list_model_adapters():
        items.append(AdapterListItem(name=name, kind="model"))
    for name in list_judge_adapters():
        items.append(AdapterListItem(name=name, kind="judge"))
    return AdapterListResponse(items=items)
