---
status: proposed
date: 2026-05-17
decision-makers: jorgejc2
---

# Code-Quality Standards

## Context and Problem Statement

The framework spans Python (backend, CLI), TypeScript/Angular (frontend), and a smaller surface of YAML, Markdown, and Dockerfiles. Requirement §6 of the high-level architecture document elevates code quality to "warrants its own ADR" status because the project will be touched by both humans and coding agents over a long horizon. Without a uniform, enforced quality bar:

- Style drifts as different contributors apply different conventions.
- Type errors leak into runtime (Pydantic catches some, but only at boundaries).
- Dead code, missing docstrings, and silent `Any` propagation accumulate, making refactors progressively riskier.
- Pre-merge review degrades into bikeshedding about formatting.

We need to commit to a specific, automatable set of tools, configurations, and conventions for every language in the repo. The high-level architecture document (§9.1–§9.3) sketches the rules; this ADR locks them in and resolves the one outstanding sub-decision: **mypy vs pyright** as the Python type checker.

## Decision Drivers

- **Strictness:** the architecture explicitly forbids `Dict[str, Any]` on public surfaces (§9.1). Whatever tools we pick must be able to enforce that bar in CI.
- **Speed:** quality tooling runs on every save (locally), every commit (pre-commit hooks), and every push (CI). Slow tooling silently encourages people to skip it.
- **Coverage of modern typing PEPs:** the backend targets Python 3.13 and uses PEP 695 generics, `Mapped[T]` from SQLAlchemy 2.x, and Protocol-based adapters. The type checker has to handle these idioms cleanly.
- **Frontend uniformity:** the Angular code already implies a Node toolchain, so adding ESLint/Prettier costs nothing extra.
- **Setup friction:** developers should be able to run all checks with a single command (`uv run check` or similar) without standing up extra services.

## Considered Options

For Python type checking specifically:

- **mypy (strict mode)**
- **pyright (strict mode)**

For everything else (linter, formatter, frontend tooling, docs format), there is one realistic choice each, captured in the Decision Outcome below.

## Decision Outcome

The full code-quality stack is:

### Python

- **Linter + formatter:** **Ruff** for both. A single `[tool.ruff]` block in `pyproject.toml` configures rule selection and formatter settings. Ruff replaces `flake8`, `isort`, `pyupgrade`, `black`, and most of `pylint`'s value in one tool.
- **Type checker:** **pyright (strict mode)**, with rationale below.
- **Docstrings:** **reStructuredText (Sphinx-flavored)** on every public class, function, and method. Private helpers may omit docstrings if the name is self-describing. Enforced via Ruff's `D` (pydocstyle) ruleset configured for the `pep257` convention with `:param:` / `:returns:` style admitted.
- **Comments:** must explain **why**, not what. The high-level architecture's §9.3 rule is binding: redundant comments that narrate code are removed in review.

### TypeScript / Angular

- **Linter:** **ESLint** with the Angular team's recommended preset (`@angular-eslint/recommended`) plus `@typescript-eslint/recommended-type-checked` for type-aware rules.
- **Formatter:** **Prettier**, integrated via `eslint-config-prettier` so ESLint and Prettier do not fight over rules.
- **TypeScript config:** `"strict": true`, `"noUncheckedIndexedAccess": true`, `"exactOptionalPropertyTypes": true`, `"noImplicitOverride": true`.
- **Docstrings:** **TSDoc** on every exported symbol.

### Cross-cutting

- **Pre-commit hooks:** orchestrated via `pre-commit` (Python framework). Hooks run Ruff (lint + format), pyright, ESLint, Prettier, and a quick `pytest` smoke marker.
- **CI:** every check that runs locally also runs in CI. CI fails on any lint, type, format, or docstring violation.
- **Single command:** `uv run check` (Python) and `npm run check` (frontend) run the full local toolchain and exit non-zero on any violation. Both are also runnable as `make check` for muscle-memory parity.

### Why pyright over mypy

The Python type checker is the only sub-decision with two genuine alternatives. The case for pyright on this project:

1. **Speed.** On a codebase the size we anticipate (backend + CLI ≈ 50–150 modules), pyright completes a full check in seconds; mypy without `dmypy` takes substantially longer (often 5–10× depending on cache state). Pyright's reactive `--watch` mode is essentially instant. Faster checks are checks that actually get run.
2. **Modern typing PEP coverage.** Pyright is the reference type checker for many recent PEPs (PEP 695 generics, PEP 696 type aliases, PEP 728 `TypedDict` extras, PEP 742 `TypeIs`). Mypy supports most of these too, but lags by months on each release. Pinning Python 3.13 means we will use these features and benefit from the faster adoption.
3. **Type narrowing precision.** Pyright's narrowing is meaningfully more precise on async code, walrus operators, and conditional `isinstance` chains. The framework is async-heavy at the adapter layer, where narrowing precision affects daily ergonomics.
4. **Strict mode is genuinely strict.** Pyright's `strict` mode flags unreachable code, unused `# type: ignore` comments, and unnecessary `cast` calls out of the box. Mypy needs `--warn-unused-ignores`, `--warn-unreachable`, and several other flags to approximate the same behavior.
5. **Pydantic v2 has native typing.** The historical reason many projects preferred mypy — its plugin for Pydantic v1 — is no longer load-bearing. Pydantic v2 ships its own `dataclass_transform`-based metaclass that both checkers handle natively. This neutralizes mypy's biggest historical advantage in our specific stack.

The case against pyright (and how we mitigate it):

- **Node.js dependency.** Pyright is written in TypeScript and historically required a Node runtime. Mitigation: install via `uv add --dev pyright` from PyPI, which packages Node internally and is invoked as `pyright` like any other Python tool. No host-level Node install is required for backend developers.
- **Smaller plugin ecosystem.** Pyright's plugin story is thinner than mypy's, but our stack (Pydantic v2 native, SQLAlchemy 2.x typed declarative, FastAPI native typing) does not need plugins. We can revisit if a future dependency is mypy-plugin-only.
- **Slightly more aggressive in strict mode.** Pyright will surface issues mypy ignores. This is a feature for a project that wants to enforce the strict-typing rule, not a bug.

The case for mypy that we explicitly weigh and reject for this project:

- It is the reference implementation cited in PEPs. True, but pyright is the type checker most heavily tested by Microsoft (Pylance) and shows up in IDE telemetry as the most-used Python type checker in 2025. Both are mainstream.
- Better community familiarity. Likely accurate, but `pyright`'s configuration surface is small and well-documented; the learning curve is not a real obstacle for either humans or agents.
- Plugin support. Already neutralized for our stack; see above.

### Consequences

- Good, because Ruff replaces a stack of separate tools (`black`, `isort`, `flake8`, `pyupgrade`, `pydocstyle`, parts of `pylint`) with a single config and one binary. Less fragmentation.
- Good, because pyright's strict mode plus the Ruff `D`/`ANN`/`PYI` rule families makes the strict-typing rule self-enforcing — the architecture's "no nested `Dict[str, Any]`" rule becomes a CI failure, not a code-review reminder.
- Good, because the same `pre-commit` framework drives both Python and TypeScript checks, giving contributors and agents a single onboarding path: `pre-commit install` once, then nothing to think about.
- Good, because `uv run check` and `npm run check` make the quality gate trivially scriptable for CI matrix steps.
- Bad, because pyright's strict mode will surface a meaningful number of issues during the first pass of any hand-rolled module. We accept this as the cost of strictness; the alternative is silent erosion.
- Bad, because Ruff's rule set evolves quickly. We will pin Ruff's version in `pyproject.toml` and update it deliberately rather than accepting "latest".
- Bad, because docstring enforcement adds friction to small refactors. The rule applies only to **public** symbols, which keeps internal helper churn cheap.
- Neutral, because Prettier and ESLint occasionally disagree about edge cases (trailing commas, line breaks). We resolve this by always letting Prettier win on formatting and ESLint win on semantics, via `eslint-config-prettier`.

## Implementation Plan

- **Affected paths**:
  - `backend/pyproject.toml` — `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.format]`, `[tool.pyright]`, `[tool.pytest.ini_options]`. No separate `mypy.ini` or `.flake8`.
  - `backend/pyrightconfig.json` — optional; only used if a setting cannot live in `pyproject.toml`. Prefer `[tool.pyright]` in `pyproject.toml`.
  - `backend/scripts/check.sh` (or a `[tool.uv.scripts]` entry) — single Python check command runner; called by `uv run check`.
  - `frontend/eslint.config.mjs` — flat-config ESLint setup including `@angular-eslint`, `@typescript-eslint`, and `eslint-config-prettier`.
  - `frontend/.prettierrc.json` — Prettier configuration.
  - `frontend/tsconfig.json` — strict TypeScript flags listed above.
  - `frontend/package.json` — `npm run check` script.
  - `.pre-commit-config.yaml` — top-level pre-commit hooks for Ruff, pyright, ESLint, Prettier, and a YAML/Markdown formatter (e.g., `prettier --write` covers Markdown too).
  - `.github/workflows/ci.yml` (or equivalent) — runs `uv run check` and `npm run check` on every PR.
- **Dependencies (Python, all dev-only)**:
  - `ruff` — pin to a specific minor version, e.g. `ruff>=0.5,<0.6`.
  - `pyright` — pin to a specific minor version, e.g. `pyright>=1.1.370,<1.2`.
  - `pre-commit` — pin to `>=3.7,<4`.
  - Stub packages as needed (`types-PyYAML`, etc.) when third-party libraries lack inline types.
- **Dependencies (frontend, all dev-only)**:
  - `eslint`, `@angular-eslint/eslint-plugin`, `@angular-eslint/template-parser`, `@typescript-eslint/parser`, `@typescript-eslint/eslint-plugin`, `eslint-config-prettier`, `prettier`. Versions track the latest compatible with the chosen Angular LTS.
- **Patterns to follow**:
  - All Python configuration lives in `pyproject.toml` `[tool.*]` blocks; do not introduce per-tool config files unless a tool genuinely cannot be configured there.
  - All Ruff rules are enabled by inclusion in a single `select` list; disabled rules are listed in `ignore` with a one-line comment explaining why. Avoid `# noqa` in source code unless the suppression is local and justified.
  - Pyright config sets `"typeCheckingMode": "strict"`, `"reportMissingTypeStubs": "error"`, `"reportImportCycles": "error"`, `"reportUnnecessaryTypeIgnoreComment": "error"`, `"reportUnnecessaryCast": "error"`.
  - Docstrings use the reStructuredText conventions documented in `aef.observability.logging` (a representative module to be referenced once it exists).
  - Frontend `tsconfig.json` enables `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noImplicitOverride`, `noFallthroughCasesInSwitch`.
  - All exported TypeScript symbols carry TSDoc with `@param`, `@returns`, and `@throws` where applicable.
- **Patterns to avoid**:
  - Do NOT introduce `black`, `isort`, `flake8`, `pyupgrade`, or `pydocstyle` as standalone tools — Ruff covers all of them.
  - Do NOT install `mypy` alongside `pyright`. Pick one type checker per repo to avoid contradictory error sets and double the CI time.
  - Do NOT add `# type: ignore` without a tracking comment (`# type: ignore[code-here]  # reason: ...`). Pyright will flag unnecessary suppressions automatically.
  - Do NOT disable Prettier rules by editing `.prettierrc.json` to allow personal preferences. Prettier's whole point is that its rules are not negotiable.
  - Do NOT add ESLint rules that conflict with Prettier formatting; use `eslint-config-prettier` to disable conflicting rules.
- **Configuration sketch (Python, `pyproject.toml`)**:

```toml
[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = [
  "E", "F", "W",      # pycodestyle, pyflakes
  "I",                # isort
  "N",                # pep8-naming
  "UP",               # pyupgrade
  "ANN",              # flake8-annotations (no missing type hints)
  "S",                # flake8-bandit (security)
  "B",                # flake8-bugbear
  "A",                # flake8-builtins
  "RUF",              # Ruff-specific
  "D",                # pydocstyle
  "PYI",              # flake8-pyi (stub files / Protocols)
]
ignore = [
  "D203",  # one-blank-line-before-class — conflicts with D211
  "D213",  # multi-line-summary-second-line — conflicts with D212
]

[tool.ruff.lint.pydocstyle]
convention = "pep257"

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.pyright]
typeCheckingMode = "strict"
pythonVersion = "3.13"
reportMissingTypeStubs = "error"
reportImportCycles = "error"
reportUnnecessaryTypeIgnoreComment = "error"
reportUnnecessaryCast = "error"
```

- **Configuration sketch (frontend, `tsconfig.json`)**:

```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "target": "ES2022",
    "moduleResolution": "bundler",
    "skipLibCheck": true
  }
}
```

- **Migration steps**: none — this is greenfield.

### Verification

- [ ] `pyproject.toml` contains `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.format]`, and `[tool.pyright]` sections that match the sketches above (or supersede them with a documented reason).
- [ ] `pyproject.toml` lists `ruff`, `pyright`, and `pre-commit` as dev dependencies with explicit upper bounds.
- [ ] `pyproject.toml` does NOT list `mypy`, `black`, `isort`, `flake8`, `pyupgrade`, or `pydocstyle` as dependencies.
- [ ] `uv run ruff check backend/src` and `uv run ruff format --check backend/src` both exit 0 on a clean tree.
- [ ] `uv run pyright backend/src` exits 0 on a clean tree.
- [ ] `frontend/tsconfig.json` enables `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, and `noImplicitOverride`.
- [ ] `frontend/eslint.config.mjs` includes `@angular-eslint`, `@typescript-eslint`, and `eslint-config-prettier`.
- [ ] `npm run check` exits 0 on a clean tree and runs ESLint + Prettier + `tsc --noEmit`.
- [ ] `.pre-commit-config.yaml` exists and `pre-commit run --all-files` exits 0 on a clean tree.
- [ ] CI fails when an `# type: ignore[...]` is unjustified (covered by `reportUnnecessaryTypeIgnoreComment`).
- [ ] CI fails when a public Python function lacks a docstring (covered by Ruff's `D` rules).
- [ ] CI fails when a TypeScript exported symbol lacks TSDoc (covered by an ESLint rule such as `tsdoc/syntax`).

## Pros and Cons of the Options

### mypy (strict mode)

- Good, because it is the reference Python type checker; PEPs are tested against it.
- Good, because of the broad ecosystem of stub packages and historical plugin support.
- Good, because configuration via `[tool.mypy]` is mature and stable.
- Neutral, because a large slice of mypy's historical advantage on this project (its Pydantic v1 plugin) is irrelevant in Pydantic v2.
- Bad, because it is meaningfully slower than pyright on cold starts; `dmypy` mitigates this only for the local case.
- Bad, because strict mode requires assembling several flags (`--strict`, `--warn-unused-ignores`, `--warn-unreachable`, `--no-implicit-optional`, etc.) to approximate pyright's defaults.
- Bad, because new typing PEPs ship in mypy on a noticeably slower cadence than pyright.

### pyright (strict mode)

- Good, because of speed: full check in seconds, watch mode is near-instant.
- Good, because strict mode is genuinely strict by default — fewer flags to remember.
- Good, because of fastest adoption of recent typing PEPs that this project will use.
- Good, because Pylance uses pyright, so editor diagnostics match CI exactly for the very common Cursor / VS Code case.
- Neutral, because configuration lives in `pyproject.toml` `[tool.pyright]` (or `pyrightconfig.json`); the surface area is small.
- Bad, because it bundles a Node.js runtime under the hood. Mitigated by installing the PyPI `pyright` package, which handles this transparently.
- Bad, because plugin ecosystem is thinner than mypy's. Not load-bearing for this stack.

## More Information

- High-level architecture: [`../high_level_architecture.md`](../high_level_architecture.md) §9.1, §9.2, §9.3, §9.5.
- External references:
  - [Ruff documentation](https://docs.astral.sh/ruff/) — Python linting and formatting.
  - [Pyright documentation](https://microsoft.github.io/pyright/) — Python static type checker selected by this ADR.
  - [BasedPyright documentation](https://docs.basedpyright.com/) — close Pyright derivative useful for understanding strict diagnostics and potential future migration.
  - [ESLint documentation](https://eslint.org/docs/latest/) — TypeScript / JavaScript linting.
  - [Prettier documentation](https://prettier.io/docs/en/) — frontend formatting.
  - [TypeScript `strict` documentation](https://www.typescriptlang.org/tsconfig/#strict) — strict-mode family of checks.
  - [Python docstring conventions (PEP 257)](https://peps.python.org/pep-0257/) — baseline docstring convention.
  - [TSDoc documentation](https://tsdoc.org/) — TypeScript doc comment format.
- Related ADRs:
  - [`0002-backend-technology-stack.md`](0002-backend-technology-stack.md) — Pydantic v2 and SQLAlchemy 2.x typed style are prerequisites for strict pyright to work cleanly.
  - [`0003-adapter-architecture-for-models-and-datasets.md`](0003-adapter-architecture-for-models-and-datasets.md) — Protocol-heavy code where pyright's narrowing precision pays off.
  - [`0011-testing-strategy-and-mock-adapters.md`](0011-testing-strategy-and-mock-adapters.md) — testing strategy reuses the same Ruff and Pyright invocations under `uv run check`.
- Revisit triggers:
  - A future dependency requires a mypy plugin and has no pyright equivalent — revisit the type-checker choice for that subsystem only or globally.
  - Ruff diverges materially from this project's style preferences for two consecutive minor releases — revisit the lint config or pin to an older line.
  - Pyright announces breaking changes to strict-mode defaults that we would not want — pin to the previous minor and re-evaluate.
