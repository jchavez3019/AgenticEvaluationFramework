"""RAG-aware metrics — DEFERRED to a future milestone.

Per ADR-0004 §4, the RAG family covers ``faithfulness``,
``answer_relevancy``, ``context_precision``, ``context_recall``, and
``retrieval_ranking``. Implementations need NLI / embedding / judge
backends that the walking skeleton does not pull in. Future milestones
land each metric behind its own module here.
"""
