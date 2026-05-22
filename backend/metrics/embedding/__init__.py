"""Embedding-based metrics — DEFERRED to a future milestone.

Per ADR-0004 §4, the embedding family ships ``semantic_sim`` and
``bertscore``. Both require ``sentence-transformers`` / ``torch`` and a
multi-hundred-MB model download on first use, which the walking
skeleton intentionally skips.

Importing this module is a no-op so ``backend.metrics`` remains light.
Future milestone implementations will register concrete metrics under
``"semantic_sim"`` and ``"bertscore"``.
"""
