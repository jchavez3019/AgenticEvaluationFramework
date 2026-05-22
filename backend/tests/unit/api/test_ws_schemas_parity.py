"""Verifies the WS schemas exactly match :class:`ProgressEvent`.

A frontend listening on ``/runs/{id}/progress`` must be able to parse
every event the engine emits. This guard test prevents accidental
drift between the engine's :data:`ProgressEvent` union and the
:mod:`backend.api.ws_schemas` re-exports.
"""

from __future__ import annotations

from typing import get_args

from backend.api import ws_schemas
from backend.engine.base import ProgressEvent


def test_ws_progress_event_matches_engine_progress_event() -> None:
    """Verify ws progress event matches engine progress event."""
    engine_members = set(get_args(ProgressEvent))
    api_members = set(get_args(ws_schemas.WSProgressEvent))
    assert engine_members == api_members


def test_each_member_is_reexported_at_module_level() -> None:
    """Verify each member is reexported at module level."""
    for cls in get_args(ProgressEvent):
        assert getattr(ws_schemas, cls.__name__) is cls
