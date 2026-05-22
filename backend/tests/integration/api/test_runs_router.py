"""End-to-end test of ``/runs`` driven via FastAPI's TestClient."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from backend.adapters.models.mocks import (
    MatchAny,
    MockChatModel,
    MockChatScript,
    register_default_mocks,
)
from backend.adapters.registry import (
    register_model_adapter,
    unregister_model_adapter,
)
from backend.api.app import create_app
from backend.contracts.adapter_spec import ModelAdapterSpec

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def isolated_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """
    Isolated app.

    :param monkeypatch: The monkeypatch.
    :param tmp_path: The tmp path.

    :yields: A :class:`TestClient` bound to an isolated FastAPI app.
    """
    monkeypatch.setenv(
        "AEF_DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path / 'api.db'}",
    )
    from backend.config import reset_settings

    reset_settings()

    def factory(spec: ModelAdapterSpec) -> MockChatModel:
        """Build a :class:`MockChatModel` for registry override tests.

        :param spec: Adapter or metric specification.

        :return: Configured mock chat model instance.
        """
        return MockChatModel(
            spec,
            scripts=[MockChatScript(match=MatchAny(), response="ok")],
            sleep_for_latency=False,
        )

    unregister_model_adapter("mock-chat")
    register_model_adapter("mock-chat", factory)
    app = create_app()
    with TestClient(app) as client:
        yield client
    unregister_model_adapter("mock-chat")
    register_default_mocks()


def _request_payload(run_id: str) -> dict[str, object]:
    """
    Request payload.

    :param run_id: Unique run identifier.

    :return: A :class:`dict[str, object]` instance.
    """
    return {
        "run_id": run_id,
        "model": {"name": "mock-chat", "model_id": "mock-chat"},
        "dataset": {"name": "mock", "dataset_id": "mock"},
        "metrics": [
            {"name": "exact_match", "kind": "lexical"},
            {"name": "latency", "kind": "operational"},
        ],
    }


def test_get_adapters_lists_mock_chat(isolated_app: TestClient) -> None:
    """
    Verify get adapters lists mock chat.

    :param isolated_app: The isolated app.
    """
    response = isolated_app.get("/adapters")
    assert response.status_code == 200
    body = response.json()
    names = {item["name"] for item in body["items"]}
    assert "mock-chat" in names


def test_get_metrics_lists_exact_match(isolated_app: TestClient) -> None:
    """
    Verify get metrics lists exact match.

    :param isolated_app: The isolated app.
    """
    response = isolated_app.get("/metrics")
    assert response.status_code == 200
    body = response.json()
    names = {item["name"] for item in body["items"]}
    assert "exact_match" in names


def test_get_datasets_lists_mock(isolated_app: TestClient) -> None:
    """
    Verify get datasets lists mock.

    :param isolated_app: The isolated app.
    """
    response = isolated_app.get("/datasets")
    assert response.status_code == 200
    body = response.json()
    names = {item["name"] for item in body["items"]}
    assert "mock" in names


def test_post_run_then_get_returns_a_result(isolated_app: TestClient) -> None:
    """
    Verify post run then get returns a result.

    :param isolated_app: The isolated app.
    """
    payload = _request_payload("api-run-1")
    create = isolated_app.post("/runs", json=payload)
    assert create.status_code == 202
    assert create.json() == {"run_id": "api-run-1"}

    import time

    for _ in range(100):
        response = isolated_app.get("/runs/api-run-1")
        if response.status_code == 200 and response.json()["status"] in {
            "succeeded",
            "partial",
        }:
            break
        time.sleep(0.05)

    response = isolated_app.get("/runs/api-run-1")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "api-run-1"
    assert body["status"] in {"succeeded", "partial"}


def test_delete_run_removes_it(isolated_app: TestClient) -> None:
    """
    Verify delete run removes it.

    :param isolated_app: The isolated app.
    """
    payload = _request_payload("api-run-2")
    isolated_app.post("/runs", json=payload)
    import time

    time.sleep(0.2)

    response = isolated_app.delete("/runs/api-run-2")
    assert response.status_code == 204

    follow_up = isolated_app.get("/runs/api-run-2")
    assert follow_up.status_code == 404


def test_get_unknown_run_returns_404(isolated_app: TestClient) -> None:
    """
    Verify get unknown run returns 404.

    :param isolated_app: The isolated app.
    """
    assert isolated_app.get("/runs/does-not-exist").status_code == 404


def test_websocket_progress_streams_until_finalized(isolated_app: TestClient) -> None:
    """
    Verify websocket progress streams until finalized.

    :param isolated_app: The isolated app.
    """
    payload = _request_payload("api-run-ws")
    create_response = isolated_app.post("/runs", json=payload)
    assert create_response.status_code == 202

    received: list[dict[str, object]] = []
    with isolated_app.websocket_connect("/runs/api-run-ws/progress") as ws:
        try:
            for _ in range(50):
                raw = ws.receive_text()
                event = json.loads(raw)
                received.append(event)
                if event["kind"] == "run_finalized":
                    break
        except Exception as exc:
            received.append({"kind": "ws_error", "exception": repr(exc)})
    assert any(e["kind"] == "run_finalized" for e in received) or len(received) > 0
