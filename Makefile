# Top-level Makefile for the Agentic Evaluation Framework (uv workspace).

.PHONY: check check-backend check-cli docstrings sync lint format type test pre-commit frontend frontend-clean

sync:
	uv sync --all-packages --all-extras --dev

docstrings:
	uv run python scripts/check_rest_docstrings.py

check: check-backend check-cli docstrings

check-backend: lint-backend format-backend type-backend test-backend

check-cli: lint-cli format-cli type-cli test-cli

lint-backend:
	cd backend && uv run ruff check . tests

format-backend:
	cd backend && uv run ruff format --check . tests

type-backend:
	cd backend && uv run pyright

test-backend:
	rm -f backend/.coverage backend/.coverage.*
	cd backend && uv run pytest

lint-cli:
	cd cli && uv run ruff check . tests

format-cli:
	cd cli && uv run ruff format --check . tests

type-cli:
	cd cli && uv run pyright

test-cli:
	rm -f cli/.coverage cli/.coverage.*
	cd cli && uv run pytest

pre-commit:
	uv tool run pre-commit run --all-files

frontend:
	@echo "frontend target is reserved; see ADR-0009"

frontend-clean:
	@echo "frontend-clean target is reserved; see ADR-0009"
