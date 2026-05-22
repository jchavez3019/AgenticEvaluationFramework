# Agentic Evaluation Framework

Text-in, text-out evaluation harness for LLMs and agentic graphs.

## Quick start

```bash
# From the repository root (uv workspace).
uv sync --all-packages --all-extras --dev

# Run checks
make check

# Headless evaluation (from repo root)
uv sync --project cli
uv run --project cli python -m cli.entrypoint --help

# API server (from repo root)
uv sync --project backend
uv run --project backend python -m backend.api.app
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [backend/README.md](backend/README.md), and [cli/README.md](cli/README.md).
