# Contributing to the Agentic Evaluation Framework

This document is the entry point for new contributors. Install dependencies
once at the repo root with `uv sync`. Run commands from that root, e.g.
`uv run --project cli python -m cli.entrypoint`. Backend details:
[`backend/README.md`](backend/README.md). CLI details: [`cli/README.md`](cli/README.md).

## Walking-skeleton status: complete

The repository ships the **walking-skeleton plan** as captured in
[`walking-skeleton-implementation_b2f0ddb9.plan.md`](.cursor/plans/walking-skeleton-implementation_b2f0ddb9.plan.md).
All milestones M0–M7 are merged and verified by CI.

Concretely, the walking skeleton delivers:

- A Pydantic v2 contracts package with the typed models that cross every
  module boundary (`backend.contracts`).
- An observability layer with structured logging, contextvars
  propagation, and a `@timed` telemetry decorator (`backend.observability`).
- A registry-driven adapter framework with deterministic mock
  implementations for chat, judge, and dataset adapters
  (`backend.adapters`).
- A persistence layer with SQLAlchemy 2.x typed models, Alembic
  migrations, and a SQLite default (`backend.persistence`).
- A metric package with lexical (`exact_match`, `token_f1`, `bleu`,
  `rouge`, …) and operational (`latency`, `cost`, `token_counts`)
  metrics, lazy-loading their heavy dependencies (`backend.metrics`).
- A single-process asyncio `LocalEngine` (`backend.engine`) plus a
  Hydra-zen-driven CLI workspace member (`cli`).
- A minimal FastAPI surface — `POST/GET/DELETE /runs`, `GET /adapters`,
  `GET /datasets`, `GET /metrics`, and `WS /runs/{id}/progress` — with
  no CORS (proxy-only per ADR-0002 / ADR-0009) (`backend.api`).

## Out of scope (deferred follow-up plans)

The following items are intentionally **not** part of the walking
skeleton. Each lands in a separate plan:

1. **Real model adapters.** HuggingFace / Ollama / OpenAI / Anthropic /
   LangGraph adapters consume the same `ModelAdapter` Protocol and
   register through the existing entry-point machinery. The mocks
   already exercise that path so adding real adapters is additive.
2. **Embedding + judge metrics.** `backend.metrics.embedding`,
   `backend.metrics.learned`, and `backend.metrics.rag` are placeholder packages
   that intentionally ship empty. The judge contract in ADR-0014 is
   modelled but no concrete `Metric` class is registered yet.
3. **Distributed engine.** ADR-0005 §4 defines a Celery + Redis-backed
   `DistributedEngine`. The `EngineConfig` discriminator already accepts
   `kind="distributed"` so wiring it is additive.
4. **Angular frontend.** `frontend/` is empty in this iteration. The API
   surface and ws-event schema are stable enough that the frontend can
   begin against `/openapi.json`.

## How to add work

1. Open or update an ADR if the work changes a cross-cutting decision.
2. Write a plan in `.cursor/plans/` that lists explicit milestones, each
   with a verification gate.
3. Implement against the existing Protocols / contracts; the registry
   layer is the canonical extension point. Avoid writing new "test mode"
   branches in production code.
4. Tests use the registry-resolved mock adapters
   (`MockChatModel`, `MockJudge`, `MockDatasetAdapter`). Never reach into
   SDK internals via `unittest.mock.patch`.
5. CI must stay green: Ruff, Pyright (strict), reST docstring policy
   (``uv run python scripts/check_rest_docstrings.py``), pytest with coverage
   ≥ 85%, and the ADR drift check.
