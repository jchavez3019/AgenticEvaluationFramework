"""Tests for :mod:`backend.observability.logging`."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from backend.observability import get_logger, run_context
from backend.observability.logging import attach_file_handler


def test_get_logger_name_equals_module_argument() -> None:
    """Verify get_logger returns a logger with the expected name."""
    log = get_logger("backend.tests.module")
    assert log.name == "backend.tests.module"


def test_attach_file_handler_writes_errors_to_file(tmp_path: Path) -> None:
    """
    Verify attach_file_handler captures ERROR+ records to a file.

    :param tmp_path: Pytest temporary directory.
    """
    log_path = tmp_path / "error.log"
    handler = attach_file_handler(log_path, level=logging.ERROR)
    try:
        log = get_logger("backend.tests.file")
        log.error("something broke")
        handler.flush()

        contents = log_path.read_text(encoding="utf-8")
        assert "something broke" in contents
    finally:
        logging.getLogger().removeHandler(handler)


def test_attach_file_handler_ignores_below_level(tmp_path: Path) -> None:
    """
    Verify attach_file_handler does NOT capture INFO records when level=ERROR.

    :param tmp_path: Pytest temporary directory.
    """
    log_path = tmp_path / "error.log"
    handler = attach_file_handler(log_path, level=logging.ERROR)
    try:
        log = get_logger("backend.tests.file.info")
        log.setLevel(logging.DEBUG)
        log.info("just info")
        handler.flush()

        contents = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        assert "just info" not in contents
    finally:
        logging.getLogger().removeHandler(handler)


async def test_run_context_attaches_fields_to_records(
    caplog_aef: pytest.LogCaptureFixture,
) -> None:
    """
    Verify run_context injects run_id, stage, sample_idx into log records.

    :param caplog_aef: Log capture fixture bound to the ``backend`` logger.
    """
    log = get_logger("backend.tests.ctx")
    async with run_context(run_id="run-X", stage="generation", sample_idx=3):
        log.info("inside")
    records = [r for r in caplog_aef.records if r.message == "inside"]
    assert records, "expected a captured record"
    record = records[-1]
    assert record.__dict__["run_id"] == "run-X"
    assert record.__dict__["stage"] == "generation"
    assert record.__dict__["sample_idx"] == 3


def test_no_print_or_basicconfig_in_backend_source() -> None:
    """ADR-0012 verification: no ``print(``, no ``logging.basicConfig`` in package code.

    ``api/app.py`` is excluded because it legitimately calls ``logging.basicConfig``
    during FastAPI startup.
    """
    src = Path(__file__).resolve().parents[3]
    package_dirs = (
        "adapters",
        "config",
        "contracts",
        "engine",
        "metrics",
        "observability",
        "persistence",
    )
    offenders: list[str] = []
    for package in package_dirs:
        pkg_path = src / package
        if not pkg_path.exists():
            continue
        for py in pkg_path.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            if "print(" in text and not py.name.startswith("test_"):
                offenders.append(f"print( in {py}")
            if "logging.basicConfig" in text:
                offenders.append(f"logging.basicConfig in {py}")
    assert not offenders, "\n".join(offenders)
