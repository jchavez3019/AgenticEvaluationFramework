"""WebSocket message schemas — strict typed envelopes.

The frontend listens on ``WS /runs/{run_id}/progress``. Every message
flowing through that socket is one of the typed events in this
module. The Angular client must mirror the same shapes; the
``ws_schemas_parity`` test verifies that the JSON encoding of each
event matches what the engine emits via :class:`ProgressSink`.

# ADR: Backend Technology Stack
# See: adr/0002-backend-technology-stack.md
"""

from __future__ import annotations

from backend.engine.base import (
    ProgressEvent,
    RunFinalized,
    SampleCompleted,
    SampleFailed,
    SampleStarted,
    StageCompleted,
    StageStarted,
)

WSProgressEvent = ProgressEvent

__all__ = [
    "RunFinalized",
    "SampleCompleted",
    "SampleFailed",
    "SampleStarted",
    "StageCompleted",
    "StageStarted",
    "WSProgressEvent",
]
