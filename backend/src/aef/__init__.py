"""Agentic Evaluation Framework — top-level package.

The :mod:`aef` package is the single Python namespace for the backend. Every
module that crosses a public boundary lives under this package and adheres to
the strict-typing rules in :doc:`adr/0010-code-quality-standards`.

This top-level module is deliberately empty; it exists only to make the
package importable. Concrete entry points (CLI, API, engine) are wired up in
their respective sub-packages.
"""

from __future__ import annotations

__all__: list[str] = []

__version__: str = "0.1.0"
