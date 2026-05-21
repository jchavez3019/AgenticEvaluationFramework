"""Learned metrics (LLM-as-judge) — DEFERRED to a future milestone.

Per ADR-0004 §4 / ADR-0014, the learned family ships ``llm_judge``,
``pairwise_judge``, and ``g_eval``. Each requires a working
``JudgeAdapter`` and Jinja-2 prompt templates with bias-mitigation
defaults; the walking skeleton's mock-judge unblocks tests today and
future milestones land the concrete metric implementations.
"""
