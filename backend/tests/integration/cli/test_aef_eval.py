"""Integration test that drives the ``aef-eval`` CLI end-to-end."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from aef.cli.entrypoint import main


@pytest.fixture
def isolated_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Force the CLI to use a temporary on-disk SQLite for the run."""
    monkeypatch.setenv(
        "AEF_DATABASE_URL",
        f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}",
    )
    monkeypatch.setenv("AEF_DATABASE_AUTO_UPGRADE", "true")
    from aef.config import reset_settings

    reset_settings()


def _write_minimal_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "run_id": "PLACEHOLDER",
                "model": {"name": "mock-chat", "model_id": "mock-chat"},
                "dataset": {"name": "mock", "dataset_id": "mock"},
                "metrics": [
                    {"name": "exact_match", "kind": "lexical"},
                    {"name": "latency", "kind": "operational"},
                ],
            },
        ),
    )


def test_aef_eval_writes_result_json(
    tmp_path: Path,
    isolated_database: Any,
) -> None:
    config = tmp_path / "config.json"
    _write_minimal_config(config)
    output_base = tmp_path / "out"

    code = main(
        [
            "--config",
            str(config),
            "--output-base",
            str(output_base),
        ],
    )

    assert code == 0
    results = list((output_base / "cli").rglob("result.json"))
    assert len(results) == 1
    payload = json.loads(results[0].read_text())
    assert payload["status"] in {"succeeded", "partial"}
    assert {m["metric_name"] for m in payload["aggregate_metric_results"]} == {
        "exact_match",
        "latency",
    }


def test_aef_eval_multirun_creates_one_directory_per_cell(
    tmp_path: Path,
    isolated_database: Any,
) -> None:
    config = tmp_path / "config.json"
    _write_minimal_config(config)
    output_base = tmp_path / "out"

    code = main(
        [
            "--config",
            str(config),
            "--output-base",
            str(output_base),
            "--multirun",
            "-O",
            "seed=1,2,3",
        ],
    )

    assert code == 0
    result_files = list((output_base / "cli").rglob("result.json"))
    assert len(result_files) == 3
    seen_seeds: set[int] = set()
    for f in result_files:
        payload = json.loads(f.read_text())
        seen_seeds.add(payload["request"]["seed"])
    assert seen_seeds == {1, 2, 3}
