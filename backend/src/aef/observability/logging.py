"""Logger factory and one-shot logging configuration.

The single logger factory is :func:`get_logger`; every module top in the
backend starts with ``logger = get_logger(__name__)``. The single
configuration entry point is :func:`configure_logging`, called exactly
once per process by the CLI / API / worker.

# ADR: Logging and Telemetry Contract
# See: adr/0012-logging-and-telemetry-contract.md
"""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aef.observability.context import ContextvarsFilter

_ROOT_LOGGER_NAME = "aef"
_CONSOLE_HANDLER_NAME = "aef.console"
_FILE_HANDLER_NAME = "aef.file"
_DEFAULT_DATE_FMT = "%Y-%m-%dT%H:%M:%S%z"

LogFormat = Literal["json", "console"]


class RotationSettings(BaseModel):
    """Rotation knobs for the optional file handler."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    backup_count: int = Field(default=5, ge=0)


class LoggingSettings(BaseModel):
    """Typed configuration consumed by :func:`configure_logging`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    format: LogFormat = "console"
    file_path: Path | None = None
    rotation: RotationSettings | None = None
    redact_secrets: bool = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger whose name equals *name*.

    The returned logger inherits the handlers attached to the root
    ``aef`` logger by :func:`configure_logging`. Module-level loggers
    have NO handlers attached directly; they propagate up. Calling this
    repeatedly is safe and cheap.

    :param name: typically ``__name__`` of the calling module.
    :returns: a configured :class:`logging.Logger`.
    """
    return logging.getLogger(name)


_SECRET_KEY_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|authorization|secret|password|bearer)",
)
_SECRET_VALUE_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|token|authorization|secret|password|bearer)" r"[\s:=]+([^\s,;\"']+)",
)
_REDACTED = "<redacted>"


class _RedactionFilter(logging.Filter):
    """Replace secret-shaped values inside log records.

    Two redactions happen:

    1. :class:`logging.LogRecord` ``extra`` values whose keys match the
       secrets allow-list become ``"<redacted>"``.
    2. The rendered message has secret-shaped substrings replaced
       (defence in depth — protects against secrets that were
       interpolated into the message body).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Mutate ``record`` to redact secret keys / values."""
        for attr_name in list(record.__dict__):
            if _SECRET_KEY_PATTERN.search(attr_name):
                setattr(record, attr_name, _REDACTED)

        if isinstance(record.msg, str):
            record.msg = _SECRET_VALUE_PATTERN.sub(
                lambda m: f"{m.group(1)}={_REDACTED}",
                record.msg,
            )
        return True


_LOG_RECORD_DEFAULT_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    },
)


class _JsonFormatter(logging.Formatter):
    """Emit one JSON line per record (no external dependency).

    Using :mod:`json` directly keeps this small and avoids drift between
    library versions of ``python-json-logger``. The shape is documented
    in ADR-0012 §2: the canonical fields (``ts``, ``level``, ``logger``,
    ``message``, ``run_id``, ``sample_idx``, ``stage``) come first, then
    any caller-supplied extras land alongside.
    """

    def format(self, record: logging.LogRecord) -> str:
        import json

        payload: dict[str, Any] = {
            "ts": self.formatTime(record, _DEFAULT_DATE_FMT),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "run_id": getattr(record, "run_id", None),
            "sample_idx": getattr(record, "sample_idx", None),
            "stage": getattr(record, "stage", None),
        }
        for key, value in record.__dict__.items():
            if key in _LOG_RECORD_DEFAULT_ATTRS or key in payload or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), default=str)


class _ConsoleFormatter(logging.Formatter):
    """Compact human-readable formatter for terminal output."""

    _BASE_FMT = "%(asctime)s %(levelname)-7s %(name)s %(_run_prefix)s%(message)s"

    def __init__(self) -> None:
        """Construct the console formatter with the project's date layout."""
        super().__init__(fmt=self._BASE_FMT, datefmt=_DEFAULT_DATE_FMT)

    def format(self, record: logging.LogRecord) -> str:
        run_id = getattr(record, "run_id", None)
        sample_idx = getattr(record, "sample_idx", None)
        stage = getattr(record, "stage", None)
        if run_id is None and sample_idx is None and stage is None:
            record.__dict__["_run_prefix"] = ""
        else:
            parts: list[str] = []
            if run_id is not None:
                parts.append(f"run={run_id[:8]}")
            if stage is not None:
                parts.append(f"stage={stage}")
            if sample_idx is not None:
                parts.append(f"sample={sample_idx}")
            record.__dict__["_run_prefix"] = "[" + " ".join(parts) + "] "
        return super().format(record)


def _make_formatter(fmt: LogFormat) -> logging.Formatter:
    if fmt == "json":
        return _JsonFormatter()
    return _ConsoleFormatter()


def configure_logging(settings: LoggingSettings | None = None) -> None:
    """Configure the root ``aef`` logger.

    Idempotent: calling this twice in the same process replaces the
    existing handlers rather than duplicating them. The CLI / API
    process call this once during startup; tests may call it inside a
    fixture.

    :param settings: typed configuration; defaults to console output at
        ``INFO`` level when omitted.
    """
    if settings is None:
        settings = LoggingSettings()

    root = logging.getLogger(_ROOT_LOGGER_NAME)
    root.setLevel(settings.level)
    root.propagate = False

    for existing in list(root.handlers):
        root.removeHandler(existing)

    formatter = _make_formatter(settings.format)
    context_filter = ContextvarsFilter()
    redaction = _RedactionFilter()

    console = logging.StreamHandler(sys.stderr)
    console.set_name(_CONSOLE_HANDLER_NAME)
    console.setLevel(settings.level)
    console.setFormatter(formatter)
    console.addFilter(context_filter)
    if settings.redact_secrets:
        console.addFilter(redaction)
    root.addHandler(console)

    if settings.file_path is not None:
        settings.file_path.parent.mkdir(parents=True, exist_ok=True)
        if settings.rotation is not None:
            file_handler: logging.Handler = RotatingFileHandler(
                filename=settings.file_path,
                maxBytes=settings.rotation.max_bytes,
                backupCount=settings.rotation.backup_count,
                encoding="utf-8",
            )
        else:
            file_handler = logging.FileHandler(
                filename=settings.file_path,
                encoding="utf-8",
            )
        file_handler.set_name(_FILE_HANDLER_NAME)
        file_handler.setLevel(settings.level)
        # File handlers always emit JSON regardless of the console
        # format so log aggregators can ingest cleanly.
        file_handler.setFormatter(_JsonFormatter())
        file_handler.addFilter(context_filter)
        if settings.redact_secrets:
            file_handler.addFilter(redaction)
        root.addHandler(file_handler)
