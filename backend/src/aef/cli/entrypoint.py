"""``aef-eval`` CLI entry point.

The CLI is intentionally thin: it parses a Hydra composition (or a
direct ``--config`` JSON file), constructs an
:class:`EvaluationRunRequest`, invokes :class:`LocalEngine`, persists
the run via :class:`SQLiteStorage`, and writes the artifact tree under
``outputs/cli/<date>/<time>-<run_id>/``.

The walking skeleton wires the bare-bones invocation; full Hydra
multirun and the rich ``configs/`` tree land in M6 follow-ups.

# ADR: CLI Configuration with Hydra and hydra-zen
# See: adr/0007-cli-configuration-with-hydra-and-hydra-zen.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml

from aef.cli.config import build_run_id
from aef.config import get_settings
from aef.contracts.run import EvaluationRunRequest, EvaluationRunResult
from aef.engine.local import LocalEngine
from aef.observability import configure_logging, get_logger
from aef.persistence import SQLiteStorage

if TYPE_CHECKING:
    from collections.abc import Iterable


logger = get_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aef-eval",
        description="Run an evaluation against a typed EvaluationRunRequest.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help=(
            "Path to a JSON / YAML file containing a serialized "
            "EvaluationRunRequest. When omitted, the CLI builds a "
            "minimal mock-driven request so a clean run smoke-tests "
            "every layer."
        ),
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Override the run identifier (default: a generated UUID).",
    )
    parser.add_argument(
        "--output-base",
        type=Path,
        default=Path("outputs"),
        help="Top-level outputs directory (default: ``outputs``).",
    )
    parser.add_argument(
        "--override",
        "-O",
        action="append",
        default=[],
        help="Hydra-style ``key=value`` overrides applied after --config.",
    )
    parser.add_argument(
        "--multirun",
        action="store_true",
        help="When combined with sweep-style overrides (e.g. ``-O foo=a,b``), "
        "execute each combination as a separate run.",
    )
    return parser


def _load_config(path: Path | None) -> dict[str, object]:
    if path is None:
        return _default_mock_request()
    text = path.read_text()
    if path.suffix in {".yaml", ".yml"}:
        loaded: object = yaml.safe_load(text)
    else:
        loaded = json.loads(text)
    if not isinstance(loaded, dict):
        raise ValueError(f"config root must be a mapping, got {type(loaded).__name__}")
    typed = cast("dict[Any, Any]", loaded)
    return {str(key): cast("object", value) for key, value in typed.items()}


def _default_mock_request() -> dict[str, object]:
    """Minimal mock request — useful for smoke testing the CLI."""
    return {
        "run_id": "PLACEHOLDER",
        "title": "mock smoke run",
        "model": {
            "name": "mock-chat",
            "model_id": "mock-chat",
        },
        "dataset": {
            "name": "mock",
            "dataset_id": "mock",
        },
        "metrics": [
            {"name": "exact_match", "kind": "lexical"},
            {"name": "latency", "kind": "operational"},
        ],
    }


def _apply_overrides(
    config: dict[str, object],
    overrides: Iterable[str],
) -> list[dict[str, object]]:
    """Apply ``--override key=value`` entries; return a list of configs."""
    parsed: list[tuple[list[str], list[str]]] = []
    for raw in overrides:
        if "=" not in raw:
            raise ValueError(f"override {raw!r} missing '='")
        key, _, value = raw.partition("=")
        keys = key.strip().split(".")
        values = [v.strip() for v in value.split(",") if v.strip()]
        parsed.append((keys, values))

    cells: list[dict[str, object]] = [dict(config)]
    for keys, values in parsed:
        new_cells: list[dict[str, object]] = []
        for cell in cells:
            for v in values:
                clone = json.loads(json.dumps(cell))
                _set_path(clone, keys, _coerce_value(v))
                new_cells.append(clone)
        cells = new_cells
    return cells


def _set_path(node: dict[str, object], keys: list[str], value: object) -> None:
    cursor: object = node
    for key in keys[:-1]:
        if not isinstance(cursor, dict):
            raise TypeError(f"cannot descend into {type(cursor).__name__}")
        cursor_dict: dict[str, object] = cursor  # type: ignore[assignment]
        if key not in cursor_dict or not isinstance(cursor_dict[key], dict):
            cursor_dict[key] = {}
        cursor = cursor_dict[key]
    if not isinstance(cursor, dict):
        raise TypeError("override target must be a mapping")
    cursor[keys[-1]] = value


def _coerce_value(raw: str) -> object:
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered == "null":
        return None
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def _resolve_request(
    config: dict[str, object],
    explicit_run_id: str | None,
) -> EvaluationRunRequest:
    if explicit_run_id is not None:
        config["run_id"] = explicit_run_id
    elif config.get("run_id") in (None, "", "PLACEHOLDER"):
        config["run_id"] = build_run_id()
    return EvaluationRunRequest.model_validate(config)


def _resolve_output_dir(base: Path, run_id: str) -> Path:
    now = datetime.now(UTC)
    return base / "cli" / now.strftime("%Y-%m-%d") / f"{now.strftime('%H-%M-%S')}-{run_id}"


async def _execute_one(
    request: EvaluationRunRequest,
    output_dir: Path,
) -> EvaluationRunResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    storage = SQLiteStorage.from_url(settings.database_url)
    try:
        await storage.create_all()
        engine = LocalEngine()
        try:
            result = await engine.run(request, storage)
        finally:
            await engine.close()
    finally:
        await storage.close()

    (output_dir / "result.json").write_text(
        result.model_dump_json(indent=2),
    )
    (output_dir / "request.json").write_text(
        request.model_dump_json(indent=2),
    )
    return result


load_config = _load_config
apply_overrides = _apply_overrides
coerce_value = _coerce_value


def run(request: EvaluationRunRequest, output_base: Path = Path("outputs")) -> EvaluationRunResult:
    """Execute a single :class:`EvaluationRunRequest` synchronously.

    This is the public library entry point — callers that already have
    a typed request use this instead of going through the CLI.
    """
    output_dir = _resolve_output_dir(output_base, request.run_id)
    return asyncio.run(_execute_one(request, output_dir))


def main(argv: list[str] | None = None) -> int:
    """Run the CLI; returns the process exit code."""
    configure_logging()
    parser = _build_parser()
    args = parser.parse_args(argv)

    config = _load_config(args.config)
    cells = _apply_overrides(config, args.override)

    if not args.multirun and len(cells) > 1:
        raise SystemExit(
            "multiple comma-separated values supplied without --multirun",
        )

    exit_code = 0
    for cell in cells:
        try:
            request = _resolve_request(
                cell,
                args.run_id if len(cells) == 1 else None,
            )
            output_dir = _resolve_output_dir(args.output_base, request.run_id)
            result = asyncio.run(_execute_one(request, output_dir))
            logger.info(
                "run finalized",
                extra={
                    "run_id": result.run_id,
                    "status": result.status,
                    "output_dir": str(output_dir),
                },
            )
        except Exception as exc:  # — top-level boundary.
            logger.exception("run failed: %s", exc)
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
