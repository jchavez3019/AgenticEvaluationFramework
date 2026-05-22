"""Model adapters — Protocols + shipped concrete implementations.

# ADR: Adapter Architecture for Models and Datasets
# See: adr/0003-adapter-architecture-for-models-and-datasets.md
"""

from __future__ import annotations

from backend.adapters.models.base import JudgeAdapter, ModelAdapter

__all__ = ["JudgeAdapter", "ModelAdapter"]
