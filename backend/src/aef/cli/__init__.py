"""Command-line entry points for evaluation runs.

The CLI uses Hydra (per ADR-0007) to compose typed Pydantic
:class:`EvaluationRunRequest` instances. ``aef-eval`` is the only
binding the user types; ``aef.cli.run(request)`` is the equivalent
library function for callers that already have a request in hand.

# ADR: CLI Configuration with Hydra and hydra-zen
# See: adr/0007-cli-configuration-with-hydra-and-hydra-zen.md
"""

from __future__ import annotations

from aef.cli.entrypoint import main, run

__all__ = ["main", "run"]
