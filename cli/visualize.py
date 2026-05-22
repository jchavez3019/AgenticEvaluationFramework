"""Post-processing CLI commands — ``aef-plot`` and ``aef-report``.

Both commands read ``outputs/cli/<...>/result.json`` produced by an
``aef-eval`` run and emit a structured rollup. The walking skeleton
ships a minimal text summary so the scripts work end-to-end; richer
Plotly figure output and HTML reports land in a follow-up milestone.

# ADR: CLI Configuration with Hydra and hydra-zen
# See: adr/0007-cli-configuration-with-hydra-and-hydra-zen.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.contracts.run import EvaluationRunResult


def _stdout(line: str) -> None:
    """
    Write ``line`` to standard output with a trailing newline.

    :param line: Line of text to emit.
    """
    sys.stdout.write(line + "\n")


def _load_result(path: Path) -> EvaluationRunResult:
    """
    Load and validate ``result.json`` at ``path``.

    :param path: Filesystem path to the artifact.

    :return: A :class:`EvaluationRunResult` instance.
    """
    payload = json.loads(path.read_text())
    return EvaluationRunResult.model_validate(payload)


def plot_main(argv: list[str] | None = None) -> int:
    """Entry point for the ``aef-plot`` console script.

    Reads ``result.json`` and prints a text summary: run id and status, then
    each aggregate metric's value and sub-scores. Plotly charts are planned
    for a later milestone.

    :param argv: Optional CLI argument vector; defaults to :data:`sys.argv`.

    :return: Process exit code (``0`` on success).
    """
    parser = argparse.ArgumentParser(prog="aef-plot")
    parser.add_argument("result_path", type=Path)
    args = parser.parse_args(argv)

    result = _load_result(args.result_path)
    _stdout(f"# {result.run_id}  status={result.status}")
    for aggregate in result.aggregate_metric_results:
        _stdout(
            f"  {aggregate.metric_name}: value={aggregate.value} "
            f"sub_values={[f'{s.name}={s.value}' for s in aggregate.sub_values]}",
        )
    return 0


def report_main(argv: list[str] | None = None) -> int:
    """
    Entry point for the ``aef-report`` console script.

    Emits a Markdown summary of the run; an HTML rendering follows in a later milestone.

    :param argv: Optional argument vector; defaults to :data:`sys.argv`.

    :return: Process exit code (``0`` on success).
    """
    parser = argparse.ArgumentParser(prog="aef-report")
    parser.add_argument("result_path", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    result = _load_result(args.result_path)
    lines: list[str] = [
        f"# Run {result.run_id}",
        f"- status: {result.status}",
        f"- started: {result.started_at.isoformat()}",
        f"- finished: {result.finished_at.isoformat()}",
        "",
        "## Aggregate metrics",
    ]
    for aggregate in result.aggregate_metric_results:
        lines.append(
            f"- **{aggregate.metric_name}** = {aggregate.value} " f"(status={aggregate.status})",
        )

    out = "\n".join(lines)
    if args.out is None:
        _stdout(out)
    else:
        args.out.write_text(out)
    return 0
