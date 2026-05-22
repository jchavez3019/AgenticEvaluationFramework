"""FastAPI application factory and ``aef-api`` entry point.

The factory wires the four routers, attaches a single
:class:`SQLiteStorage` instance to ``app.state``, and registers a
lifespan that creates the schema on startup and disposes the engine on
shutdown. Per ADR-0002 the application does NOT enable CORS — the
frontend reaches the API exclusively through the Angular dev-server
proxy.

# ADR: Backend Technology Stack
# See: adr/0002-backend-technology-stack.md
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from backend.api.routers import adapters, datasets, metrics, runs
from backend.config import get_settings
from backend.observability import configure_logging, get_logger
from backend.persistence import SQLiteStorage

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    Initialize storage on startup; flush it on shutdown.

    :param app: FastAPI application instance.

    :yields: Nothing; runs startup then teardown around the serving window.
    """
    settings = get_settings()
    storage = SQLiteStorage.from_url(settings.database_url)
    await storage.create_all()
    app.state.storage = storage
    logger.info(
        "api startup",
        extra={"database_url": settings.database_url},
    )
    try:
        yield
    finally:
        await storage.close()
        logger.info("api shutdown")


def create_app() -> FastAPI:
    """
    Build a fresh :class:`FastAPI` application.

    :return: :class:`FastAPI` instance.
    """
    configure_logging()
    app = FastAPI(
        title="Agentic Evaluation Framework API",
        version="0.1.0",
        lifespan=_lifespan,
    )
    app.include_router(adapters.router)
    app.include_router(datasets.router)
    app.include_router(metrics.router)
    app.include_router(runs.router)
    return app


app = create_app()


def run() -> None:
    """
    Entry point for the ``aef-api`` console script.

    Starts a uvicorn server bound to ``127.0.0.1:8000`` (the Angular dev-server proxies
    through ``host.docker.internal:8000``, per ADR-0009).

    """
    import uvicorn

    uvicorn.run(
        "backend.api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
