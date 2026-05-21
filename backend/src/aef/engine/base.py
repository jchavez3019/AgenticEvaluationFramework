"""Engine Protocol + typed progress events.

# ADR: Execution Engine — Local and Distributed
# See: adr/0005-execution-engine-local-and-distributed.md
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from aef.contracts.primitives import EngineConfig
    from aef.contracts.run import EvaluationRunRequest, EvaluationRunResult
    from aef.persistence.base import StorageAdapter


class _BaseProgressEvent(BaseModel):
    """Common base for typed progress events."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1)
    emitted_at: datetime


class StageStarted(_BaseProgressEvent):
    """A pipeline stage has started for ``run_id``."""

    kind: Literal["stage_started"] = "stage_started"
    stage: str


class StageCompleted(_BaseProgressEvent):
    """A pipeline stage has finished for ``run_id``."""

    kind: Literal["stage_completed"] = "stage_completed"
    stage: str
    duration_ms: Annotated[float, Field(ge=0.0)]


class SampleStarted(_BaseProgressEvent):
    """The engine has begun processing a sample."""

    kind: Literal["sample_started"] = "sample_started"
    sample_idx: Annotated[int, Field(ge=0)]
    stage: str


class SampleCompleted(_BaseProgressEvent):
    """The engine has finished a sample successfully."""

    kind: Literal["sample_completed"] = "sample_completed"
    sample_idx: Annotated[int, Field(ge=0)]
    stage: str
    duration_ms: Annotated[float, Field(ge=0.0)]


class SampleFailed(_BaseProgressEvent):
    """A sample failed during processing."""

    kind: Literal["sample_failed"] = "sample_failed"
    sample_idx: Annotated[int, Field(ge=0)]
    stage: str
    exception_class: str
    exception_message: str


class RunFinalized(_BaseProgressEvent):
    """The run finalized; its summary status is in ``status``."""

    kind: Literal["run_finalized"] = "run_finalized"
    status: Literal["succeeded", "partial", "failed", "cancelled"]


ProgressEvent = (
    StageStarted | StageCompleted | SampleStarted | SampleCompleted | SampleFailed | RunFinalized
)


@runtime_checkable
class ProgressSink(Protocol):
    """Receives typed progress events emitted by an :class:`ExecutionEngine`."""

    async def emit(self, event: ProgressEvent) -> None:
        """Emit one progress event."""
        ...


@runtime_checkable
class ExecutionEngine(Protocol):
    """The contract every engine implementation satisfies."""

    @property
    def spec(self) -> EngineConfig:
        """The engine's typed configuration."""
        ...

    async def run(
        self,
        request: EvaluationRunRequest,
        storage: StorageAdapter,
        progress: ProgressSink | None = None,
    ) -> EvaluationRunResult:
        """Drive the run end-to-end and return the populated result."""
        ...

    async def cancel(self, run_id: str) -> None:
        """Request a cooperative cancellation of an in-flight run."""
        ...

    async def close(self) -> None:
        """Flush worker pools and release any held resources."""
        ...
