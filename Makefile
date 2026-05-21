# Top-level Makefile for the Agentic Evaluation Framework.
#
# `make check` runs the full local quality gate (lint + types + tests).
# Sub-targets exist so CI and IDE save hooks can call individual phases.

.PHONY: check check-backend lint format type test pre-commit frontend frontend-clean

check: check-backend ## run all backend checks

check-backend: lint format type test ## ruff + pyright + pytest in backend/

lint:
	cd backend && uv run ruff check src tests

format:
	cd backend && uv run ruff format --check src tests

type:
	cd backend && uv run pyright src

test:
	cd backend && uv run pytest

pre-commit:
	uv run pre-commit run --all-files

frontend: ## placeholder; populated in a future plan
	@echo "frontend target is reserved; the Angular app lives in frontend/ once ADR-0008/0009 ship"

frontend-clean: ## placeholder; populated in a future plan
	@echo "frontend-clean target is reserved; populated alongside the frontend Docker setup (ADR-0009)"
