"""Shared FastAPI dependency-injection helpers.

# ADR: Backend Technology Stack
# See: adr/0002-backend-technology-stack.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from fastapi import Request

if TYPE_CHECKING:
    from backend.persistence.sqlite import SQLiteStorage


def get_storage(request: Request) -> SQLiteStorage:
    """
    Return the :class:`SQLiteStorage` attached to ``app.state``.

    :param request: Evaluation run request payload.

    :return: :class:`SQLiteStorage` instance.
    """
    return cast("SQLiteStorage", request.app.state.storage)
