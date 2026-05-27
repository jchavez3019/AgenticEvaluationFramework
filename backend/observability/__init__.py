"""Observability primitives — logging, contextvars, timing, telemetry.

This package owns logging configuration and timing for the entire
backend. Every module imports its logger via :func:`get_logger`; every
phase that wants to land in :class:`TelemetryReport` is wrapped in
``with timed("phase"):`` or decorated with :func:`timed`.

Public surface:

- :func:`get_logger` — module-scoped logger factory.
- :func:`attach_file_handler` — append a file handler to the root logger.
- :func:`run_context` — async context manager that injects
  ``run_id`` / ``stage`` / ``sample_idx`` into log records and timing
  records.
- :func:`timed` — decorator and context manager for timing.
- :class:`TelemetryRecorder` — stores :class:`TimingRecord` per run;
  :meth:`TelemetryRecorder.dump_run` returns the final
  :class:`TelemetryReport`.
- :func:`start_span` — OpenTelemetry reservation; no-op until
  ``AEF_OTEL_ENABLED=1``.

# ADR: Logging and Telemetry Contract
# See: adr/0012-logging-and-telemetry-contract.md
"""

from __future__ import annotations

from backend.observability.context import (
    ContextvarsFilter,
    RunContext,
    current_context,
    run_context,
)
from backend.observability.logging import (
    attach_file_handler,
    get_logger,
)
from backend.observability.telemetry import start_span
from backend.observability.timing import TelemetryRecorder, timed

__all__ = [
    "ContextvarsFilter",
    "RunContext",
    "TelemetryRecorder",
    "attach_file_handler",
    "current_context",
    "get_logger",
    "run_context",
    "start_span",
    "timed",
]
