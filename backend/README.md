# Agentic Evaluation Framework — Backend

Python 3.13 backend for the Agentic Evaluation Framework. Owns the evaluation
contracts, adapters, execution engine, persistence layer, CLI, and API.

## Quick start

```bash
cd backend

# Install runtime + dev dependencies (uv resolves Python 3.13 automatically).
uv sync

# Verify the environment.
uv run python -c "import aef; print(aef.__version__)"

# Run the lint / type / format checks (Ruff + Pyright).
uv run ruff check src tests
uv run ruff format --check src tests
uv run pyright src

# Run the test suite (default markers exclude gpu / network / broker / docker).
uv run pytest
```

The repo-root `Makefile` wraps these as `make check`.

## Layout (root-peers, per high_level_architecture.md §2.2)

```
backend/
├── pyproject.toml      # single source of truth for deps + tooling config
├── uv.lock             # committed lockfile
├── src/aef/            # package code
│   ├── api/            # FastAPI app (M7)
│   ├── cli/            # Hydra CLI (M6)
│   ├── adapters/       # adapter framework + mocks (M3)
│   ├── contracts/      # Pydantic v2 contracts (M1)
│   ├── engine/         # LocalEngine (M6) / DistributedEngine (later)
│   ├── metrics/        # lexical / operational / etc. (M5+)
│   ├── observability/  # logging, context, timing (M2)
│   └── persistence/    # SQLAlchemy + Alembic (M4)
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
└── README.md
```

## Walking-skeleton status

The walking-skeleton plan (`walking-skeleton-implementation_b2f0ddb9.plan.md`)
is **complete**. All milestones M0–M7 ship in this repository:

| Milestone | Scope                               | Status   |
| --------- | ----------------------------------- | -------- |
| M0        | Repo bootstrap + tooling            | complete |
| M1        | Pydantic contracts                  | complete |
| M2        | Observability (logging + telemetry) | complete |
| M3        | Adapter framework + mocks           | complete |
| M4        | Persistence + Alembic               | complete |
| M5        | Lexical + operational metrics       | complete |
| M6        | LocalEngine + Hydra CLI             | complete |
| M7        | Minimal FastAPI                     | complete |

Subsequent work proceeds in **separate** plans. The following are
explicitly **deferred** out of the walking skeleton and land in follow-up
plans (see `CONTRIBUTING.md`):

- Real model adapters (HuggingFace / Ollama / OpenAI / Anthropic / LangGraph).
- Embedding + judge metric families (`embedding/`, `learned/`, `rag/` are
  registered but empty).
- :class:`DistributedEngine` (Celery + Redis worker pool, GPU pinning).
- Angular frontend (`frontend/` is empty in this iteration).

## Smoke tests

End-to-end smoke tests against the in-tree mocks:

```bash
# Library / CLI smoke — runs against MockChatModel + MockDatasetAdapter,
# persists to SQLite, writes outputs/cli/<...>/result.json.
AEF_DATABASE_URL=sqlite+aiosqlite:///:memory: \
    uv run aef-eval --config ../configs/eval_run.yaml \
    --output-base /tmp/aef-cli-smoke

# CLI multirun — three runs with different seeds.
AEF_DATABASE_URL=sqlite+aiosqlite:///:memory: \
    uv run aef-eval --config ../configs/eval_run.yaml \
    --output-base /tmp/aef-cli-multirun --multirun -O seed=1,2,3

# API smoke — start the FastAPI server.
uv run aef-api  # binds to 127.0.0.1:8000
```

`/openapi.json` returns a valid OpenAPI 3.1 document with `/runs`,
`/runs/{id}`, `/adapters`, `/datasets`, `/metrics`, and the
`/runs/{id}/progress` websocket.

## Conventions

- Every entry-point file carries a `# ADR: <title>` and `# See: adr/<file>.md`
  reference comment. Drift is a CI failure.
- No `Dict[str, Any]` on public surfaces (per ADR-0010); promote nested
  dictionaries to Pydantic sub-models.
- `with timed("phase"):` and `get_logger(__name__)` are the only sanctioned
  timing and logging primitives (per ADR-0012).
- Tests use registry-resolved mock adapters — never `unittest.mock.patch` of
  an SDK internal (per ADR-0011).
