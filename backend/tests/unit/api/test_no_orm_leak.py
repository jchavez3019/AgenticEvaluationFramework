"""Guard that no SQLAlchemy ORM type leaks through API responses.

ADR-0006 §6 requires the persistence layer to project ORM rows back
into Pydantic records before they cross any module boundary. The
guards below walk the FastAPI route table and assert every declared
``response_model`` is a Pydantic ``BaseModel`` rather than an ORM
declarative class.
"""

from __future__ import annotations

import inspect
import typing

from fastapi.routing import APIRoute
from pydantic import BaseModel
from sqlalchemy.orm import DeclarativeBase

from backend.api.app import create_app


def test_no_orm_leak_through_response_models() -> None:
    """Verify no orm leak through response models."""
    app = create_app()
    offenders: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        candidate = route.response_model
        if candidate is None:
            continue
        for cls in _candidate_classes(candidate):
            if inspect.isclass(cls) and issubclass(cls, DeclarativeBase):
                offenders.append(f"{route.path} -> {cls}")
            if inspect.isclass(cls) and not (issubclass(cls, BaseModel) or cls is type(None)):
                if cls.__module__.startswith("backend.persistence.orm"):
                    offenders.append(f"{route.path} -> ORM class {cls}")
    assert not offenders, "\n".join(offenders)


def _candidate_classes(candidate: object) -> list[object]:
    """
    Candidate classes.

    :param candidate: The candidate.

    :return: A :class:`list[object]` instance.
    """
    args = list(typing.get_args(candidate))
    return args or [candidate]
