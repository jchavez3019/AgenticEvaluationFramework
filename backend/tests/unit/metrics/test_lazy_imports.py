"""Verify ``import aef.metrics`` does not pull heavy upstream libraries.

Per ADR-0004 §6: ``Each metric module's heavy upstream library is NOT
imported at the top of the file (verifiable via grep + an import test
that asserts only stdlib + pydantic are pulled by the bare ``import
aef.metrics``).``
"""

from __future__ import annotations

import subprocess
import sys
import textwrap


def test_importing_aef_metrics_does_not_import_heavy_libs() -> None:
    """A subprocess imports ``aef.metrics`` and dumps ``sys.modules`` keys."""
    code = textwrap.dedent(
        """
        import sys
        import aef.metrics  # noqa: F401

        forbidden = {
            "sacrebleu",
            "rouge_score",
            "nltk",
            "rapidfuzz",
            "sentence_transformers",
            "bert_score",
            "transformers",
            "torch",
        }
        leaked = sorted(forbidden.intersection(sys.modules))
        if leaked:
            sys.exit("LEAKED: " + ",".join(leaked))
        sys.exit(0)
        """,
    )
    result = subprocess.run(  # noqa: S603 — args are a fixed allowlist.
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"unexpected stdout/err: {result.stdout!r} / {result.stderr!r}"
