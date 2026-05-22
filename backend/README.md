# Agentic Evaluation Framework — Backend

Python 3.13 backend library and FastAPI API for the Agentic Evaluation Framework.

## Quick start

From the **repository root** (uv workspace):

```bash
uv sync --all-packages --all-extras --dev

uv run --package backend python -c "import backend; print(backend.__version__)"

# Run the lint / type / format checks (Ruff + Pyright).
uv run --package backend ruff check . tests
uv run --package backend pyright
# Run the test suite (default markers exclude gpu / network / broker / docker).
uv run --package backend pytest
```

The repo-root `Makefile` runs `make check` for backend and cli.

## Layout (root-peers, per high_level_architecture.md §2.2)

```
backend/
├── pyproject.toml      # distribution name: backend
├── contracts/          # Pydantic v2 contracts
├── api/                # FastAPI app
├── engine/
├── persistence/
├── adapters/
├── metrics/
├── observability/
├── config/
└── tests/
```

Headless evaluation lives in the sibling [`cli/`](../cli/) workspace member.

## Smoke tests

```bash
# API (from repo root)
uv run --project backend python -m backend.api.app

# CLI (from repo root; see cli/README.md)
AEF_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  uv run --project cli python -m cli.entrypoint \
  output.base_dir=/tmp/aef-cli-smoke
```

See [`cli/README.md`](../cli/README.md) for more CLI examples.
