"""Verifies the FastAPI app emits a valid OpenAPI document."""

from __future__ import annotations

from aef.api.app import create_app


def test_openapi_document_lists_runs_and_registries() -> None:
    app = create_app()
    schema = app.openapi()
    assert schema["openapi"].startswith("3.")
    paths = schema["paths"]
    assert "/runs" in paths
    assert "/runs/{run_id}" in paths
    assert "/adapters" in paths
    assert "/datasets" in paths
    assert "/metrics" in paths


def test_no_cors_middleware_is_installed() -> None:
    app = create_app()
    middleware_repr = " ".join(repr(m) for m in app.user_middleware)
    assert "CORSMiddleware" not in middleware_repr
