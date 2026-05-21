"""FastAPI routers — one per resource family.

Each router declares its prefix and tags so the OpenAPI grouping is
predictable. The ``aef.api.app`` factory mounts them in order.

# ADR: Backend Technology Stack
# See: adr/0002-backend-technology-stack.md
"""

from __future__ import annotations

from aef.api.routers import adapters, datasets, metrics, runs

__all__ = ["adapters", "datasets", "metrics", "runs"]
