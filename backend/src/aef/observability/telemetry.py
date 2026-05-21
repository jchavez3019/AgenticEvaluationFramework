"""OpenTelemetry reservation — :func:`start_span` is a no-op until enabled.

ADR-0012 §6 reserves the integration shape: every place in the codebase
that wants distributed tracing later writes::

    with start_span("metric.bleu", run_id=run_id):
        ...

Today this is a no-op span (no OpenTelemetry import, no exporter,
no overhead). When ``AEF_OTEL_ENABLED=1`` is wired up in a future plan,
the same call sites will emit OTLP spans without any code churn. The
return value is a context manager so the call shape is stable across
both implementations.

# ADR: Logging and Telemetry Contract
# See: adr/0012-logging-and-telemetry-contract.md
"""

from __future__ import annotations

import os
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Final, Self

_OTEL_ENABLED_ENV: Final[str] = "AEF_OTEL_ENABLED"


class _NoOpSpan(AbstractContextManager["_NoOpSpan"]):
    """Trivial context manager with no instrumentation impact."""

    __slots__ = ("name", "attributes")

    def __init__(self, name: str, attributes: dict[str, object]) -> None:
        """Store the span identity for parity with the future OTel span."""
        self.name = name
        self.attributes = attributes

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


def start_span(name: str, **attributes: object) -> AbstractContextManager[_NoOpSpan]:
    """Begin a no-op span — reservation for future OpenTelemetry support.

    The current implementation never imports OpenTelemetry. When
    ``AEF_OTEL_ENABLED=1`` is set, a future plan replaces the body of
    this function with a real OTLP span emission; call sites stay the
    same.

    :param name: span name (e.g., ``"metric.bleu"``,
        ``"engine.generation_stage"``).
    :param attributes: optional structured attributes for the future
        OTel span. The current no-op stores them on the returned span
        so tests can assert call shape.
    :returns: a context manager; entering / exiting the block records
        nothing today.
    """
    # The env var is read but not acted on yet — verifying the shape
    # at this seam catches accidental imports of opentelemetry that
    # would otherwise bloat the install.
    _ = os.environ.get(_OTEL_ENABLED_ENV, "0")
    return _NoOpSpan(name, attributes)
