"""Integration test that drives the Hydra CLI end-to-end."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from cli.entrypoint import main


@pytest.fixture
def isolated_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    Force the CLI to use a temporary on-disk SQLite for the run.

    :param monkeypatch: Pytest monkeypatch fixture.
    :param tmp_path: Pytest temporary directory path.

    :return: :class:`None` instance.
    """
    monkeypatch.setenv(
        "AEF_DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}",
    )
    monkeypatch.setenv("AEF_DATABASE_AUTO_UPGRADE", "true")
    from backend.config import reset_settings

    reset_settings()


def test_aef_eval_writes_result_json(
    tmp_path: Path,
    isolated_database: Any,
) -> None:
    """
    Verify aef eval writes result json.

    :param tmp_path: The tmp path.
    :param isolated_database: The isolated database.
    """
    output_base = tmp_path / "out"

    code = main(
        [
            "aef-eval",
            f"output.base_dir={output_base}",
        ],
    )

    assert code == 0
    results = list((output_base / "cli").rglob("result.json"))
    assert len(results) == 1
    payload = json.loads(results[0].read_text())
    assert payload["status"] in {"succeeded", "partial"}
    assert {m["metric_name"] for m in payload["aggregate_metric_results"]} == {
        "exact_match",
        "token_f1",
        "latency",
    }


def test_aef_eval_multirun_creates_one_directory_per_cell(
    tmp_path: Path,
    isolated_database: Any,
) -> None:
    """
    Verify aef eval multirun creates one directory per cell.

    :param tmp_path: The tmp path.
    :param isolated_database: The isolated database.
    """
    output_base = tmp_path / "out"

    code = main(
        [
            "aef-eval",
            f"output.base_dir={output_base}",
            "seed=1,2,3",
            "--multirun",
        ],
    )

    assert code == 0
    result_files = list((output_base / "cli").rglob("result.json"))
    assert len(result_files) == 3
    seen_seeds: set[int] = set()
    for result_file in result_files:
        payload = json.loads(result_file.read_text())
        seen_seeds.add(payload["request"]["seed"])
    assert seen_seeds == {1, 2, 3}
