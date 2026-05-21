"""Tests for :mod:`aef.observability.logging`."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from aef.observability import (
    LoggingSettings,
    configure_logging,
    get_logger,
    run_context,
)


def test_get_logger_name_equals_module_argument() -> None:
    log = get_logger("aef.tests.module")
    assert log.name == "aef.tests.module"


def test_configure_logging_is_idempotent() -> None:
    configure_logging()
    handler_count_first = len(logging.getLogger("aef").handlers)
    configure_logging()
    handler_count_second = len(logging.getLogger("aef").handlers)
    assert handler_count_first == handler_count_second


def test_console_format_smoke(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(LoggingSettings(format="console"))
    log = get_logger("aef.tests.console")
    log.info("hello")
    captured = capsys.readouterr()
    assert "hello" in captured.err
    assert "aef.tests.console" in captured.err


def test_json_format_emits_valid_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(LoggingSettings(format="json"))
    log = get_logger("aef.tests.json")
    log.info("payload")
    captured = capsys.readouterr().err.strip()
    assert captured, "expected at least one log line"
    line = captured.splitlines()[-1]
    parsed = json.loads(line)
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "aef.tests.json"
    assert parsed["message"] == "payload"
    assert parsed["run_id"] is None


async def test_run_context_attaches_fields_to_records(
    caplog_aef: pytest.LogCaptureFixture,
) -> None:
    log = get_logger("aef.tests.ctx")
    async with run_context(run_id="run-X", stage="generation", sample_idx=3):
        log.info("inside")
    records = [r for r in caplog_aef.records if r.message == "inside"]
    assert records, "expected a captured record"
    record = records[-1]
    assert record.__dict__["run_id"] == "run-X"
    assert record.__dict__["stage"] == "generation"
    assert record.__dict__["sample_idx"] == 3


def test_redaction_filter_replaces_secret_extras(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(LoggingSettings(format="json"))
    log = get_logger("aef.tests.redact")
    log.info("authenticated", extra={"api_key": "sk-very-secret"})
    captured = capsys.readouterr().err.strip()
    assert "sk-very-secret" not in captured
    assert "<redacted>" in captured


def test_redaction_filter_replaces_secret_in_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(LoggingSettings(format="json"))
    log = get_logger("aef.tests.redact")
    log.info("connected with api_key=sk-very-secret to provider")
    captured = capsys.readouterr().err.strip()
    assert "sk-very-secret" not in captured
    assert "<redacted>" in captured


def test_file_handler_emits_json_lines(tmp_path: Path) -> None:
    log_path = tmp_path / "run.log"
    configure_logging(
        LoggingSettings(format="console", file_path=log_path),
    )
    log = get_logger("aef.tests.file")
    log.info("from-file")

    for handler in logging.getLogger("aef").handlers:
        handler.flush()

    contents = log_path.read_text(encoding="utf-8").strip()
    assert contents, "expected file output"
    line = contents.splitlines()[-1]
    parsed = json.loads(line)
    assert parsed["message"] == "from-file"


def test_no_print_or_basicconfig_in_aef_source() -> None:
    """ADR-0012 verification: no ``print(``, no ``logging.basicConfig``."""
    src = Path(__file__).resolve().parents[3] / "src" / "aef"
    offenders: list[str] = []
    for py in src.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if "print(" in text and not py.name.startswith("test_"):
            offenders.append(f"print( in {py}")
        if "logging.basicConfig" in text:
            offenders.append(f"logging.basicConfig in {py}")
    assert not offenders, "\n".join(offenders)
