"""Unit tests for :mod:`cli.visualize` entry points."""

from __future__ import annotations

from pathlib import Path

import pytest
from cli.visualize import plot_main, report_main


def _golden_result_path() -> Path:
    """
    Return the backend golden ``run_result.json`` path.

    :return: Filesystem path to the golden run-result fixture.
    """
    return Path(__file__).resolve().parents[3] / "backend" / "tests" / "fixtures" / "golden" / "run_result.json"


def test_plot_main_emits_text_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    Verify ``plot_main`` emits a human-readable summary.

    :param capsys: Pytest capture fixture for stdout.
    """
    code = plot_main([str(_golden_result_path())])
    assert code == 0
    output = capsys.readouterr().out
    assert "status=" in output
    assert "exact_match" in output


def test_report_main_writes_markdown_file(tmp_path: Path) -> None:
    """
    Verify ``report_main`` writes Markdown when ``--out`` is provided.

    :param tmp_path: Pytest temporary directory.
    """
    out = tmp_path / "report.md"
    code = report_main([str(_golden_result_path()), "--out", str(out)])
    assert code == 0
    assert out.exists()
    body = out.read_text(encoding="utf-8")
    assert body.startswith("# Run ")
    assert "## Aggregate metrics" in body


def test_report_main_emits_markdown_to_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """
    Verify ``report_main`` emits Markdown to stdout without ``--out``.

    :param capsys: Pytest capture fixture for stdout.
    """
    code = report_main([str(_golden_result_path())])
    assert code == 0
    output = capsys.readouterr().out
    assert output.startswith("# Run ")
    assert "## Aggregate metrics" in output
