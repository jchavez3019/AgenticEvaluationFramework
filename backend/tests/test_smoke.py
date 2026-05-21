"""Bootstrap smoke test verifying the package imports cleanly."""

from __future__ import annotations

import importlib


def test_aef_importable() -> None:
    module = importlib.import_module("aef")
    assert module.__version__ == "0.1.0"
