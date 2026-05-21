"""Tests for the OpenTelemetry no-op reservation in
:mod:`aef.observability.telemetry`.
"""

from __future__ import annotations

import sys

from aef.observability import start_span


def test_start_span_is_a_no_op_context_manager() -> None:
    with start_span("metric.bleu", run_id="r-1") as span:
        assert span.name == "metric.bleu"
        assert span.attributes == {"run_id": "r-1"}


def test_start_span_does_not_import_opentelemetry() -> None:
    with start_span("metric.placeholder"):
        pass
    # No OpenTelemetry module should be imported by the no-op span,
    # so the framework can stay slim until the OTel feature lands.
    assert "opentelemetry" not in sys.modules
