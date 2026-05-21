"""FastAPI surface — wraps the persistence + engine in HTTP/WS endpoints.

# ADR: Backend Technology Stack
# See: adr/0002-backend-technology-stack.md
"""

from __future__ import annotations

from aef.api.app import app, create_app, run

__all__ = ["app", "create_app", "run"]
