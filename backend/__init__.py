"""Agentic Evaluation Framework — backend library package.

The :mod:`backend` package is the Python library for adapters, engines,
metrics, persistence, and the FastAPI API. Every module that crosses a
public boundary adheres to the strict-typing rules in
:doc:`adr/0010-code-quality-standards`.

This top-level module is deliberately minimal; concrete entry points (API,
engine) live in sub-packages. The Hydra CLI is the separate ``cli``
workspace member.
"""

from __future__ import annotations

__all__: list[str] = []

__version__: str = "0.1.0"
