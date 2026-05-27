"""``aef-eval`` CLI entry point.

Hydra composes YAML under ``configs/``; overrides use Hydra's native CLI
(``model=mock``, ``sampling.temperature=0.7``, ``--multirun``, …).
The composed config is validated as :class:`EvaluationRunRequest`, then
:class:`LocalEngine` runs the evaluation and writes artifacts under
Hydra's managed output directory.

# ADR: CLI Configuration with Hydra and hydra-zen
# See: adr/0007-cli-configuration-with-hydra-and-hydra-zen.md
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, cast

import hydra
from backend.config import get_settings
from backend.contracts.run import EvaluationRunRequest, EvaluationRunResult
from backend.engine.local import LocalEngine
from backend.observability import get_logger
from backend.observability.logging import attach_file_handler
from backend.persistence import SQLiteStorage
from hydra.core.hydra_config import HydraConfig
from omegaconf import DictConfig, OmegaConf

from cli.config import build_run_id, register_configs

logger = get_logger(__name__)

_CONFIG_DIR = str(Path(__file__).resolve().parent.parent / "configs")

# Populate hydra-zen's named store before Hydra composes the config tree.
register_configs()


def request_from_cfg(cfg: DictConfig) -> EvaluationRunRequest:
    """
    Resolve a Hydra composition into a typed :class:`EvaluationRunRequest`.

    :param cfg: Hydra-composed configuration tree.

    :return: The validated evaluation run request.
    """
    resolved = OmegaConf.to_container(cfg, resolve=True)
    if not isinstance(resolved, dict):
        msg = f"config root must be a mapping, got {type(resolved).__name__}"
        raise TypeError(msg)
    payload = cast("dict[str, Any]", resolved)
    run_id = payload.get("run_id")
    if run_id in (None, "", "PLACEHOLDER"):
        payload["run_id"] = build_run_id()
    return EvaluationRunRequest.model_validate(payload)


async def _execute_one(
    request: EvaluationRunRequest,
    output_dir: Path,
) -> EvaluationRunResult:
    """
    Execute a single :class:`EvaluationRunRequest` asynchronously.

    :param request: The evaluation run request.
    :param output_dir: Directory where ``result.json`` and ``request.json`` are written.
    :return: The evaluation run result.
    """
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


def run(
    request: EvaluationRunRequest,
    output_dir: Path | None = None,
) -> EvaluationRunResult:
    """
    Execute a single :class:`EvaluationRunRequest` synchronously.

    Library callers that already hold a typed request use this instead of going
    through Hydra.

    :param request: Fully specified :class:`EvaluationRunRequest`.
    :param output_dir: Explicit output directory. Falls back to
        ``<request.output.base_dir>/<run_id>/`` when ``None``.
    :return: The evaluation run result.
    """
    if output_dir is None:
        output_dir = Path(request.output.base_dir) / request.run_id
    return asyncio.run(_execute_one(request, output_dir))


def _run_from_cfg(cfg: DictConfig) -> int:
    """
    Run one Hydra-composed evaluation; return a process exit code.

    :param cfg: Hydra-composed configuration tree.

    :return: Process exit code (``0`` on success).
    """
    output_dir = Path(HydraConfig.get().runtime.output_dir)
    error_handler = attach_file_handler(output_dir / "error.log")
    try:
        request = request_from_cfg(cfg)
        result = asyncio.run(_execute_one(request, output_dir))
        logger.info(
            "run finalized",
            extra={
                "run_id": result.run_id,
                "status": result.status,
                "output_dir": str(output_dir),
            },
        )
        return 0
    except Exception:
        logger.exception("CRITICAL: Backend crashed with an unhandled exception")
        return 1
    finally:
        logging.getLogger().removeHandler(error_handler)


@hydra.main(
    config_path=_CONFIG_DIR,
    config_name="eval_run",
    version_base="1.3",
)
def hydra_entry(cfg: DictConfig) -> int:
    """
    Hydra-decorated task: one composed config per invocation (incl. multirun).

    :param cfg: Hydra-composed configuration tree.

    :return: Process exit code (``0`` on success).
    """
    return _run_from_cfg(cfg)


def main(argv: list[str] | None = None) -> int:
    """
    Run the CLI via Hydra; returns the process exit code.

    :param argv: Optional argument vector; defaults to :data:`sys.argv`.

    :return: Process exit code (``0`` on success).
    """
    if argv is not None:
        sys.argv = list(argv)
    try:
        hydra_entry()
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
