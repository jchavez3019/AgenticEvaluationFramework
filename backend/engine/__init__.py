"""Execution engine — Protocol + ``LocalEngine`` (asyncio).

# ADR: Execution Engine — Local and Distributed
# See: adr/0005-execution-engine-local-and-distributed.md
"""

from __future__ import annotations

from backend.engine.base import (
    ExecutionEngine,
    ProgressEvent,
    ProgressSink,
    RunFinalized,
    SampleCompleted,
    SampleFailed,
    SampleStarted,
    StageCompleted,
    StageStarted,
)
from backend.engine.local import LocalEngine

__all__ = [
    "ExecutionEngine",
    "LocalEngine",
    "ProgressEvent",
    "ProgressSink",
    "RunFinalized",
    "SampleCompleted",
    "SampleFailed",
    "SampleStarted",
    "StageCompleted",
    "StageStarted",
]
