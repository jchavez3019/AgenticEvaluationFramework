"""Verify ``import backend.metrics`` does not pull heavy upstream libraries.

Per ADR-0004 §6: ``Each metric module's heavy upstream library is NOT
imported at the top of the file (verifiable via grep + an import test
that asserts only stdlib + pydantic are pulled by the bare ``import
backend.metrics``).``
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


def test_importing_backend_metrics_does_not_import_heavy_libs() -> None:
    """
    A subprocess imports ``backend.metrics`` and dumps ``sys.modules`` keys.

    :return: :class:`None` instance.
    """
    import shutil

    code = textwrap.dedent(
        """
        import sys
        import backend.metrics  # noqa: F401

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
    uv_path = shutil.which("uv")
    assert uv_path is not None, "uv must be on PATH"
    repo_root = Path(__file__).resolve().parents[4]
    result = subprocess.run(  # noqa: S603 — args are a fixed allowlist.
        [uv_path, "run", "--package", "backend", "python", "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"unexpected stdout/err: {result.stdout!r} / {result.stderr!r}"
