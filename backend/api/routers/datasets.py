"""``GET /datasets`` — registered dataset adapters.

# ADR: Backend Technology Stack
# See: adr/0002-backend-technology-stack.md
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.adapters.registry import list_dataset_adapters
from backend.api.schemas import AdapterListItem, AdapterListResponse

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("", response_model=AdapterListResponse)
async def get_datasets() -> AdapterListResponse:
    """
    List every registered dataset adapter, by name.

    :return: :class:`AdapterListResponse` instance.
    """
    return AdapterListResponse(
        items=[AdapterListItem(name=name, kind="dataset") for name in list_dataset_adapters()],
    )
