# Agentic Evaluation Framework — CLI

Hydra-driven headless evaluation CLI. Depends on the [`backend`](../backend/) workspace package.

## Quick start

From the **repository root**:

```bash
uv sync --project cli

uv run --project cli python -m cli.entrypoint --help

AEF_DATABASE_URL=sqlite+aiosqlite:///:memory: \
  uv run --project cli python -m cli.entrypoint \
  output.base_dir=/tmp/aef-cli-smoke

# Hydra overrides (see adr/0007-cli-configuration-with-hydra-and-hydra-zen.md)
uv run --project cli python -m cli.entrypoint sampling=greedy
uv run --project cli python -m cli.entrypoint seed=0,1,2 --multirun
```

## Layout

```
cli/
├── pyproject.toml
├── entrypoint.py       # python -m cli.entrypoint
├── config.py           # hydra-zen registration
├── visualize.py        # aef-plot, aef-report
└── tests/
```
