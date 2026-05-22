"""Command-line entry points for evaluation runs.

The CLI uses Hydra (per ADR-0007) to compose typed Pydantic
:class:`EvaluationRunRequest` instances. Run evaluations with
``python -m cli.entrypoint`` (see :mod:`cli.entrypoint`).

# ADR: CLI Configuration with Hydra and hydra-zen
# See: adr/0007-cli-configuration-with-hydra-and-hydra-zen.md
"""

from __future__ import annotations

__all__: list[str] = []
