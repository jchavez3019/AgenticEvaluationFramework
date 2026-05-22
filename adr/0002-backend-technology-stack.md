---
status: proposed
date: 2026-05-17
decision-makers: jorgejc2
---

# Backend Technology Stack

## Context and Problem Statement

The Agentic Evaluation Framework backend has to do all of the following:

- Run evaluation pipelines that load Hugging Face, Ollama, cloud-API, and LangGraph models.
- Expose a typed HTTP and WebSocket API so the Angular dashboard can submit runs and stream progress.
- Be importable as a plain Python library so the CLI can drive headless runs without going through the network.
- Persist every run to a structured store that the dashboard can query, while also producing on-disk artifacts under `outputs/` for CLI users.
- Validate every input and output with explicit, machine-readable contracts (no ad-hoc dictionaries crossing module boundaries).

Before any feature work can begin we need to commit to a concrete language version, web framework, package manager, validation library, ORM, and migration tool. Each of these choices is hard to reverse later because dozens of files will be written against them, and they constrain every other ADR (adapters, persistence, execution engine).

The high-level architecture document (`../high_level_architecture.md` §3, §6, §10) establishes these choices in summary form. This ADR is the canonical decision record.

## Decision

The backend will be built on the following stack:

- **Language:** Python, constrained to `>=3.13,<3.14`. Pinning the minor range protects us from breaking changes in dependencies that are slow to support new Python releases.
- **Web framework:** FastAPI. Used for both the HTTP API and the WebSocket endpoints described in `high_level_architecture.md` §5.2.
- **Package and environment manager:** `uv`. `pyproject.toml` is the single source of truth for dependencies; `uv.lock` is committed. No `requirements.txt` files are maintained alongside it.
- **Data validation:** Pydantic v2. Every public function signature, every API request/response, every adapter method, and every persisted record is typed with a Pydantic model or a typed dataclass. No `Dict[str, Any]` crosses a module boundary; nested dictionaries must be promoted to a Pydantic sub-model.
- **ORM:** SQLAlchemy 2.x using its typed declarative style (`mapped_column`, `Mapped[T]`).
- **Schema migrations:** Alembic, configured to use the SQLAlchemy metadata as its source.
- **Default database:** SQLite (embedded). Postgres is the documented swap-in path for any future workload that exceeds SQLite's single-writer limitations. The persistence ADR (`0006`) covers the storage layer in detail.
- **Async runtime:** `asyncio`. All adapter and engine boundaries are async by default; CPU-bound metric work runs under `asyncio.to_thread` or a process pool when needed.
- **Project layout:** uv workspace at the repo root (`pyproject.toml` with `[tool.uv.workspace] members = ["backend", "cli"]`; committed `uv.lock` at root). The backend distribution is named `backend` (import root `backend`); modules live flat beside `backend/pyproject.toml` (`backend/contracts/`, `backend/api/`, …). The CLI is a separate workspace member at `cli/` (import root `cli`; depends on `backend` via `[tool.uv.sources] backend = { workspace = true }`). `configs/`, `outputs/`, `Makefile`, `.pre-commit-config.yaml`, `.github/workflows/`, and `frontend/` are repo-root peers. The CLI resolves `configs/` via a workspace-root anchor relative to the repo root.
- **API CORS posture (v1):** the FastAPI server does **not** enable CORS. The frontend reaches the backend exclusively through the Angular dev server's proxy (`/api`, `/ws` → `host.docker.internal:8000`, per [ADR-0009](0009-frontend-docker-dev-environment.md)). Browser clients hitting `http://localhost:8000` directly from a different origin are intentionally blocked. A future production deployment with a real cross-origin client would open a follow-up ADR to introduce a CORS allowlist.

Non-goals:

- We are NOT adopting Flask, Django, Starlette directly, or any framework other than FastAPI for the API surface.
- We are NOT adopting `poetry`, `pip-tools`, `pipenv`, `conda`, `pdm`, or `hatch` for environment management.
- We are NOT using Pydantic v1 syntax. New code uses v2 idioms (`field_validator`, `model_validator`, `BaseModel.model_dump`).
- We are NOT using raw `sqlite3` or hand-written SQL outside of explicitly performance-critical paths. Queries go through SQLAlchemy.
- We are NOT supporting Python versions below 3.13 in v1. Older runtimes can be revisited in a future ADR if a hard requirement appears.

## Consequences

- Good, because every choice in this stack has first-class typing support and aligns with the strict-typing rule in `high_level_architecture.md` §9.1.
- Good, because FastAPI's Pydantic integration removes most of the boilerplate around request/response validation and OpenAPI generation.
- Good, because `uv` is significantly faster than `pip`/`poetry` for environment creation and lockfile resolution, which directly improves CI and developer iteration time.
- Good, because SQLAlchemy 2.x typed style works cleanly with Pyright strict (locked in [ADR-0010](0010-code-quality-standards.md)), and Alembic's autogenerate support lets schema changes ride alongside model changes in normal pull requests.
- Bad, because `uv` is a younger tool than `poetry` or `pip-tools`. We accept a small ecosystem-maturity risk in exchange for performance and ergonomics.
- Bad, because pinning Python to `>=3.13,<3.14` will exclude users on older interpreters. This is a deliberate cost — it lets us use modern typing features (PEP 695 generics, improved `TypeAlias`, `typing.override`) without conditional imports.
- Bad, because requiring Pydantic models on every boundary adds upfront friction compared to passing dictionaries around. The strict-typing ADR (`0010`) explains why we accept that cost.
- Neutral, because choosing SQLite as the default DB does not preclude Postgres later. The ORM and migration tooling are identical in either direction; only the connection URL changes.

## Implementation Plan

- **Affected paths**:
  - `backend/pyproject.toml` — declares Python `>=3.13,<3.14` in `[project.requires-python]`, lists all runtime and dev dependencies, configures `uv` build backend, Ruff, and Pyright (per ADR-0010).
  - `uv.lock` (repo root) — workspace lockfile from `uv lock` at the repository root.
  - `backend/` — flat package tree (`backend/contracts/`, `backend/api/`, …) per `high_level_architecture.md` §3.1.
  - `backend/api/app.py` — FastAPI app factory.
  - `backend/persistence/orm.py` — SQLAlchemy 2.x typed declarative base and ORM classes.
  - `backend/persistence/migrations/` — Alembic environment (`env.py`, `script.py.mako`, `versions/`).
  - `backend/contracts/` — Pydantic models for `EvaluationRunRequest`, `EvaluationRunResult`, `EvaluationSample`, `GenerationRequest`, `GenerationResponse`, `MetricResult`, adapter specs.
  - `cli/` — Hydra CLI workspace member (see ADR-0007).
  - `backend/README.md` — bootstrap: `uv sync` at repo root, `uv run --package backend aef-api`.
- **Dependencies (initial pin set; exact patch versions resolved by `uv lock`)**:
  - Runtime: `fastapi>=0.115`, `uvicorn[standard]>=0.30`, `pydantic>=2.7,<3`, `sqlalchemy>=2.0,<3`, `alembic>=1.13`, `aiosqlite>=0.20` (for async SQLAlchemy on SQLite), `httpx>=0.27` (used by adapters; also FastAPI's TestClient), `python-multipart>=0.0.9` (for any future file uploads).
  - Dev: `pytest>=8`, `pytest-asyncio>=0.23`, `pytest-cov>=5`, `ruff>=0.5`, `pyright>=1.1.370` (per ADR-0010), `pre-commit>=3.7`, `types-requests` and similar stub packages as needed.
  - Specific model-runtime SDKs (`transformers`, `ollama`, `openai`, `anthropic`, `langgraph`) are scoped to optional dependency groups in `pyproject.toml` so that someone running only mock-based tests does not have to install GPU stacks.
- **Patterns to follow**:
  - All dependency changes go through `uv add` / `uv add --dev` so `pyproject.toml` and `uv.lock` stay in sync.
  - All ORM models inherit from a single typed `Base = DeclarativeBase` declared once in `persistence/models.py`.
  - All API request and response shapes live in `aef.contracts`. The API layer (`aef.api.schemas`) re-uses contract models or defines thin wrappers; it does not invent new shapes.
  - All FastAPI route handlers use Pydantic models in their signatures so OpenAPI generation is automatic.
  - All async DB sessions are created via a single `aef.persistence.session.SessionLocal` factory and consumed via FastAPI dependency injection.
- **Patterns to avoid**:
  - Do NOT call `pip install` directly inside this repo or commit a `requirements.txt`.
  - Do NOT define ORM models with the legacy `Column(...)` style; use the typed `Mapped[T]` / `mapped_column(...)` style throughout.
  - Do NOT mix Pydantic v1 idioms (`@validator`, `Config` class) with v2 idioms.
  - Do NOT reach into Alembic's generated SQL by hand to bypass migrations; if a migration is wrong, write a new one.
  - Do NOT write raw `sqlite3` calls in business logic; always go through SQLAlchemy.
- **Configuration**:
  - `pyproject.toml` declares `requires-python = ">=3.13,<3.14"`.
  - `pyproject.toml [tool.ruff]`, `[tool.pyright]`, and `[tool.pytest.ini_options]` are configured per [ADR-0010](0010-code-quality-standards.md) (code quality) and [ADR-0011](0011-testing-strategy-and-mock-adapters.md) (testing).
  - Database URL is provided via an environment variable (`AEF_DATABASE_URL`), defaulting to `sqlite+aiosqlite:///./.aef/aef.sqlite3` for local development.
- **Migration steps**: none — this is greenfield. Future schema changes ship as Alembic revisions inside `backend/src/aef/persistence/migrations/versions/`.

### Verification

- [ ] `uv --version` is available in the developer environment and `uv sync` succeeds at the repo root after `pyproject.toml` is added.
- [ ] `python --version` reports a 3.13.x interpreter inside the `uv`-managed venv.
- [ ] `pyproject.toml` contains `requires-python = ">=3.13,<3.14"` and lists FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic, and `uv`-compatible build settings.
- [ ] `uv.lock` is present and committed.
- [ ] `uv run python -c "import fastapi, pydantic, sqlalchemy, alembic; assert pydantic.VERSION.startswith('2.')"` succeeds.
- [ ] `uv run alembic upgrade head` runs cleanly against the default SQLite URL once the first migration exists.
- [ ] `uv run uvicorn aef.api.app:app --reload` starts the API server; `GET /openapi.json` returns a valid OpenAPI document.
- [ ] No file under `backend/src/aef/` imports `sqlite3` directly (verifiable via grep).
- [ ] No file under `backend/src/aef/` uses Pydantic v1 idioms (`@validator`, `class Config:` inside `BaseModel` subclasses).

## Alternatives Considered

- **Flask + marshmallow**: rejected. Flask lacks first-class async support; marshmallow does not integrate with the typing ecosystem as cleanly as Pydantic.
- **Django + DRF**: rejected. Too heavyweight for an evaluation framework. Most of Django's value (admin, auth, ORM scaffolding) is irrelevant here, and we would still need to bolt async support on top.
- **Starlette directly**: rejected. FastAPI is a thin layer on top of Starlette and is what we would essentially rebuild ourselves; using FastAPI directly is strictly cheaper.
- **`poetry` instead of `uv`**: rejected. `uv` is markedly faster, has compatible `pyproject.toml` semantics, and is now stable enough for production use in similar projects.
- **Raw `sqlite3` + hand-written SQL**: rejected. The persistence layer is non-trivial (`runs`, `samples`, `metric_results`, metadata tables) and we want type-safe queries plus migrations. SQLAlchemy 2.x covers both without forcing us to leave Python.
- **Tortoise ORM / SQLModel**: considered. SQLModel is appealing because it unifies Pydantic and SQLAlchemy, but its momentum lags behind SQLAlchemy 2.x's native typed style, and we would still need Alembic for migrations. We prefer keeping ORM (SQLAlchemy) and validation (Pydantic) explicitly separate to avoid coupling our public contracts to our database schema.

## More Information

- High-level architecture: [`../high_level_architecture.md`](../high_level_architecture.md) §3, §6, §10.
- External references:
  - [Python documentation](https://docs.python.org/3/) — language runtime and typing features.
  - [FastAPI documentation](https://fastapi.tiangolo.com/) — backend API framework and OpenAPI generation.
  - [`uv` documentation](https://docs.astral.sh/uv/) — Python package and environment manager.
  - [Pydantic v2 documentation](https://docs.pydantic.dev/latest/) — typed validation and data contracts.
  - [SQLAlchemy 2.0 documentation](https://docs.sqlalchemy.org/en/20/) — ORM / Core persistence layer.
  - [Alembic documentation](https://alembic.sqlalchemy.org/) — database migrations.
  - [SQLite documentation](https://www.sqlite.org/docs.html) — embedded database engine.
- Related ADRs:
  - [`0003-adapter-architecture-for-models-and-datasets.md`](0003-adapter-architecture-for-models-and-datasets.md) — depends on Pydantic models defined here.
  - [`0006-persistence-sqlite-default-postgres-swap-in.md`](0006-persistence-sqlite-default-postgres-swap-in.md) — extends the SQLAlchemy / SQLite choice.
  - [`0010-code-quality-standards.md`](0010-code-quality-standards.md) — finalizes the Ruff / Pyright configuration referenced in this ADR.
- Revisit triggers:
  - Python 3.14 reaches general availability and our dependency stack supports it — bump the upper bound.
  - A meaningful fraction of evaluation runs require concurrent multi-writer access to the database — revisit Postgres-as-default.
  - `uv` deprecates a feature this stack relies on — revisit the package-manager choice.
