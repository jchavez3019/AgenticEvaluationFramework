"""``/runs`` resource: create, fetch, delete, and progress streaming.

The HTTP routes use :class:`SQLiteStorage` (injected via
:func:`get_storage`) to persist runs and reach into
:class:`LocalEngine` to drive them. The websocket endpoint attaches a
:class:`ProgressSink` that forwards events as JSON.

# ADR: Backend Technology Stack
# See: adr/0002-backend-technology-stack.md
# ADR: Execution Engine — Local and Distributed
# See: adr/0005-execution-engine-local-and-distributed.md
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from aef.api.dependencies import get_storage
from aef.api.schemas import (
    CreateRunResponse,
    EvaluationRunRequest,
    EvaluationRunResult,
    RunListPage,
    RunQuery,
)
from aef.contracts.persistence import RunStatus
from aef.contracts.primitives import EngineKind
from aef.engine.base import ProgressEvent
from aef.engine.local import LocalEngine
from aef.observability import get_logger

if TYPE_CHECKING:
    from aef.persistence.sqlite import SQLiteStorage

logger = get_logger(__name__)

router = APIRouter(prefix="/runs", tags=["runs"])


_progress_subscribers: dict[str, list[asyncio.Queue[ProgressEvent | None]]] = {}
_progress_lock = asyncio.Lock()
_inflight_tasks: set[asyncio.Task[None]] = set()


class _BroadcastSink:
    """Fan-out :class:`ProgressSink` shared by HTTP execution and WS clients."""

    def __init__(self, run_id: str) -> None:
        self._run_id = run_id

    async def emit(self, event: ProgressEvent) -> None:
        """Push ``event`` to every subscriber registered for the run."""
        async with _progress_lock:
            subscribers = list(_progress_subscribers.get(self._run_id, []))
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "ws subscriber queue full; dropping event",
                    extra={"run_id": self._run_id, "kind": event.kind},
                )


async def _subscribe(run_id: str) -> asyncio.Queue[ProgressEvent | None]:
    queue: asyncio.Queue[ProgressEvent | None] = asyncio.Queue(maxsize=256)
    async with _progress_lock:
        _progress_subscribers.setdefault(run_id, []).append(queue)
    return queue


async def _unsubscribe(
    run_id: str,
    queue: asyncio.Queue[ProgressEvent | None],
) -> None:
    async with _progress_lock:
        if run_id in _progress_subscribers:
            try:
                _progress_subscribers[run_id].remove(queue)
            except ValueError:
                pass
            if not _progress_subscribers[run_id]:
                _progress_subscribers.pop(run_id, None)


async def _signal_completion(run_id: str) -> None:
    async with _progress_lock:
        subscribers = list(_progress_subscribers.get(run_id, []))
    for queue in subscribers:
        try:
            queue.put_nowait(None)
        except asyncio.QueueFull:
            pass


def _spawn_run_task(
    run_id: str,
    request: EvaluationRunRequest,
    storage: SQLiteStorage,
) -> None:
    """Schedule the run on the running asyncio loop and dispatch progress."""
    sink = _BroadcastSink(run_id)
    engine = LocalEngine()

    async def _runner() -> None:
        try:
            await engine.run(request, storage, progress=sink)
        except Exception:
            logger.exception("run %s crashed", run_id)
        finally:
            await engine.close()
            await _signal_completion(run_id)

    task = asyncio.create_task(_runner())
    _inflight_tasks.add(task)
    task.add_done_callback(_inflight_tasks.discard)


StorageDep = Annotated["SQLiteStorage", Depends(get_storage)]


@router.post("", response_model=CreateRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_run(
    request: EvaluationRunRequest,
    storage: StorageDep,
) -> CreateRunResponse:
    """Persist the request and schedule the run on the local engine."""
    _spawn_run_task(request.run_id, request, storage)
    return CreateRunResponse(run_id=request.run_id)


@router.get("/{run_id}", response_model=EvaluationRunResult)
async def get_run(
    run_id: str,
    storage: StorageDep,
) -> EvaluationRunResult:
    """Fetch the (possibly in-progress) :class:`EvaluationRunResult`."""
    try:
        return await storage.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"run {run_id!r} not found",
        ) from exc


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run(
    run_id: str,
    storage: StorageDep,
) -> None:
    """Hard-delete a run and its descendants."""
    try:
        await storage.delete_run(run_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"run {run_id!r} not found",
        ) from exc


PageQ = Annotated[int, Query(ge=1)]
LimitQ = Annotated[int, Query(ge=1, le=200)]
StatusQ = Annotated[RunStatus | None, Query(alias="status")]
EngineQ = Annotated[EngineKind | None, Query()]
StringQ = Annotated[str | None, Query()]


@router.get("", response_model=RunListPage)
async def list_runs(  # — many filter query params.
    storage: StorageDep,
    page: PageQ = 1,
    limit: LimitQ = 25,
    run_status: StatusQ = None,
    engine_kind: EngineQ = None,
    model_name: StringQ = None,
    dataset_name: StringQ = None,
    text: StringQ = None,
) -> RunListPage:
    """Paginated listing of stored runs."""
    return await storage.list_runs(
        RunQuery(
            page=page,
            limit=limit,
            status=run_status,
            engine_kind=engine_kind,
            model_name=model_name,
            dataset_name=dataset_name,
            text=text,
        ),
    )


@router.websocket("/{run_id}/progress")
async def ws_progress(websocket: WebSocket, run_id: str) -> None:
    """Stream progress events for ``run_id`` as JSON-encoded messages."""
    await websocket.accept()
    queue = await _subscribe(run_id)
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            await websocket.send_text(event.model_dump_json())
    except WebSocketDisconnect:
        pass
    finally:
        await _unsubscribe(run_id, queue)
        try:
            await websocket.close()
        except RuntimeError:
            pass
