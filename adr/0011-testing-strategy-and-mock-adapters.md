---
status: proposed
date: 2026-05-17
decision-makers: jorgejc2
---

# Testing Strategy and Mock Adapters

## Context and Problem Statement

LLM evaluation is, by nature, expensive: real models cost money (cloud APIs), GPU time (local HF / Ollama), or both. A test suite that requires real models to run is a test suite that nobody runs locally and that flakes in CI. At the same time, an evaluation framework lives or dies by correctness — we cannot rely on "looks right" because the unit under test is the thing that decides whether a *model* is right.

The high-level architecture document (§9.4) lays out the constraints:

- `pytest` is the only test runner.
- Two non-negotiable mocks: `MockChatModel` and `MockJudge`. Both are first-class adapters, registered in the same registry as real adapters.
- Hardware/network-bound tests are gated behind `pytest` markers (`@pytest.mark.gpu`, `@pytest.mark.network`) and excluded from default CI.
- Default local model for end-to-end smoke tests: SmolLM via the Hugging Face adapter (decided separately in ADR-0013).

We need to lock in:

1. The directory layout and discovery rules.
2. The mocking contract — how `MockChatModel` and `MockJudge` are configured per-test, and what determinism guarantees they make.
3. The marker taxonomy and how CI selects which tests to run.
4. The fixtures every contributor and agent can rely on.
5. The minimum coverage targets a PR must satisfy to merge.

Without an explicit ADR, every contributor will invent their own mocking style ("I'll just patch `httpx.AsyncClient`...") and the test suite will fragment.

## Decision

Adopt the following test architecture for the backend (and CLI, which imports the backend as a library). The frontend has its own testing story, separately decided in the frontend ADR (`0008`).

### 1. Directory layout

```
backend/
  tests/
    conftest.py                      # shared session-level fixtures
    unit/                            # pure-Python, no I/O, no models
      adapters/                      # adapter shape tests
      contracts/                     # Pydantic schema round-trips
      engine/                        # Local engine state machine
      metrics/                       # metric math correctness with seeded inputs
      observability/                 # logging, timing, contextvars
      persistence/                   # SQLAlchemy ORM + repository tests against in-memory SQLite
    integration/                     # multi-component, still mock-driven by default
      cli/
      api/
      engine_local/
      engine_distributed/            # gated behind @pytest.mark.broker
    smoke/                           # end-to-end, real-model, gated
      smollm/                        # gated behind @pytest.mark.gpu
      cloud/                         # gated behind @pytest.mark.network
    fixtures/
      datasets/                      # tiny seeded CSVs, JSONL files
      responses/                     # canned outputs for MockChatModel scripted maps
      configs/                       # YAML configs used by Hydra-driven tests
```

The split is layered: `unit/` tests can be run in seconds with no external dependencies; `integration/` exercises wiring (engine ↔ adapter ↔ persistence) using mocks; `smoke/` exercises real models and is opt-in.

### 2. Marker taxonomy

Markers are declared in `pyproject.toml` `[tool.pytest.ini_options]` with `--strict-markers` enabled, so an unknown marker is a test failure.

| Marker             | Meaning                                                                    | CI default |
| ------------------ | -------------------------------------------------------------------------- | ---------- |
| (no marker)        | Pure unit / mock-driven integration test. Always runs.                     | run        |
| `@pytest.mark.slow`| > 1s expected. Runs in PR CI but isolated in its own job.                  | run        |
| `@pytest.mark.gpu` | Requires a CUDA-capable GPU and the `models-hf` optional group installed.  | skipped    |
| `@pytest.mark.network`| Hits a real cloud API. Requires network and credentials.                | skipped    |
| `@pytest.mark.broker`| Requires Redis to be reachable (for `DistributedEngine` tests).          | skipped    |
| `@pytest.mark.docker`| Spins up a Docker container during the test.                             | skipped    |

CI runs `pytest -m "not gpu and not network and not broker and not docker"` by default. A separate scheduled CI job runs the gated suites against a hosted runner with the appropriate environment.

### 3. Mock adapter contracts

`MockChatModel` and `MockJudge` are real members of the adapter registry from ADR-0003 — the engine and metric code do not branch on whether an adapter is mock or real. Their distinguishing feature is configurability.

#### `MockChatModel`

Construction shape (illustrative):

```python
class MockChatScript(BaseModel):
    """A mapping rule from request to response."""
    match: MockMatch  # tagged-union: ExactPrefix | Regex | Callable | Any
    response: str
    latency_ms: float = 0.0
    fail_with: str | None = None  # exception class name to raise instead

class MockChatModelConfig(ModelAdapterSpec):
    kind: Literal["mock-chat"]
    scripts: list[MockChatScript]
    seed: int = 0  # makes any randomized response deterministic
```

Behavior:

- Requests are matched against `scripts` in order; the first match wins.
- If no script matches, the adapter raises `MockChatModelError` (no silent fallthrough). Tests must be exhaustive about expected inputs.
- Latency simulation is wall-clock by default (so timing tests are realistic) but can be virtualized via a fixture that monkeypatches `asyncio.sleep`.
- `fail_with` lets a test simulate adapter failures (timeouts, schema errors) without fragile mocking of underlying SDKs.

Determinism: with the same `scripts`, `seed`, and request stream, `MockChatModel` produces byte-identical outputs.

#### `MockJudge`

Same shape, specialized for LLM-as-judge metrics:

```python
class MockJudgeScript(BaseModel):
    match: MockMatch  # matches against (input, candidate, reference) tuple
    rubric: RubricScore  # the structured judgment

class MockJudgeConfig(JudgeAdapterSpec):
    kind: Literal["mock-judge"]
    scripts: list[MockJudgeScript]
    seed: int = 0
```

`RubricScore` is the same Pydantic model the real judge adapter would return — mock and real are interchangeable from the metric's perspective.

### 4. Fixtures

A small set of fixtures live in `tests/conftest.py` and are documented as the canonical way to write tests:

- `mock_chat(scripts: list[MockChatScript]) -> MockChatModel` — factory fixture that registers a clean `MockChatModel` per test.
- `mock_judge(scripts: list[MockJudgeScript]) -> MockJudge` — analogous for the judge.
- `tiny_dataset(rows: int = 5) -> DatasetAdapter` — returns a `MockDatasetAdapter` with seeded rows.
- `in_memory_db() -> AsyncSession` — yields an async SQLAlchemy session bound to `sqlite+aiosqlite:///:memory:` with all migrations applied.
- `tmp_outputs(tmp_path) -> Path` — Hydra-style `outputs/<date>/<time>/` tree under `tmp_path`.
- `caplog_aef(caplog) -> AEFCapLog` — wrapper around `caplog` that asserts on `aef`-namespaced records and surfaces `run_id`/`stage`/`sample_idx` from the contextvars filter (per ADR-0012).
- `local_engine(...) -> LocalEngine` — factory that produces a `LocalEngine` wired to mock adapters and an in-memory DB.

All fixtures are typed; none return `dict` or untyped tuples.

### 5. Coverage target

- `pytest --cov=aef --cov-fail-under=85` enforces ≥85% line coverage on `aef.*` for the default (mock-driven) test selection. Smoke tests are not counted (their job is end-to-end correctness, not coverage).
- Branches and exception paths must be covered for every adapter, every metric, the engine state machine, and the persistence layer. Coverage is necessary but not sufficient — review still focuses on whether tests exercise the *behavior* and not just the *lines*.

### 6. Determinism rules

- Every test that involves randomness sets a seed via the relevant primitive (`numpy.random.default_rng(0)`, `random.Random(0)`, `torch.manual_seed(0)` only inside `@pytest.mark.gpu` tests).
- No test uses real wall-clock time as a correctness signal. Time-sensitive assertions go through `freezegun` or a `frozen_time()` fixture.
- No test depends on filesystem ordering. Use `sorted()` or explicit ordering when comparing directory listings.
- No test reaches the network without `@pytest.mark.network`.

### Non-goals

- We are NOT adopting `unittest`-style test classes. `pytest` function-level tests are the convention.
- We are NOT supporting `tox` for matrix testing in v1. `uv` + a single Python version is enough.
- We are NOT building a custom mocking framework. `MockChatModel` and `MockJudge` are configured Pydantic objects, not a test DSL.
- We are NOT enforcing a coverage gate above 85% in v1. The threshold can rise later as the suite stabilizes.

## Consequences

- Good, because the mock adapters are real adapters: any test using them exercises the full engine → adapter → metric → persistence path. There is no "test mode" branch in production code.
- Good, because the marker taxonomy makes the default CI fast and reliable. Contributors and agents do not pay for GPU/network costs they did not opt into.
- Good, because typed fixtures (`mock_chat`, `mock_judge`, `local_engine`, etc.) give every test a known good starting point. A new test rarely needs to wire much itself.
- Good, because the determinism rules eliminate the most common flake sources before they appear.
- Bad, because writing a `MockChatScript` for a complex prompt structure is more verbose than a one-line `@patch` decorator. We accept this — the verbosity buys us correctness when the prompt structure changes.
- Bad, because the 85% coverage gate will occasionally feel arbitrary on small refactors. The threshold is on the project, not the file; localized dips are fine if the global average holds.
- Neutral, because the smoke suite is gated rather than removed. Real-model tests still exist and run in scheduled CI; they just do not block PRs.

## Implementation Plan

- **Affected paths**:
  - `backend/pyproject.toml` — `[tool.pytest.ini_options]` registering markers, `--strict-markers`, `addopts = "-ra --cov=aef --cov-fail-under=85 -m 'not gpu and not network and not broker and not docker'"`.
  - `backend/tests/conftest.py` — shared fixtures.
  - `backend/tests/unit/`, `backend/tests/integration/`, `backend/tests/smoke/`, `backend/tests/fixtures/` — per the layout above.
  - `backend/src/aef/adapters/models/mocks.py` — `MockChatModel`, `MockJudge`, their config models, and registry registration.
  - `backend/src/aef/adapters/datasets/mocks.py` — `MockDatasetAdapter`.
  - `.github/workflows/ci.yml` (or equivalent) — default job runs the un-gated suite; a separate scheduled job runs gated markers.
  - `docs/testing.md` (optional) — a short contributor guide pointing at fixtures and showing canonical examples.
- **Dependencies (all dev-only)**:
  - `pytest>=8`, `pytest-asyncio>=0.23`, `pytest-cov>=5`, `pytest-randomly>=3.15` (re-orders tests to surface order-coupled flakes), `freezegun>=1.5` (for time-frozen tests).
  - No `mock` or `pytest-mock` — the mock adapters cover the realistic surface; ad-hoc patching is discouraged.
- **Patterns to follow**:
  - One test file per public module under test, mirroring the source layout (`tests/unit/adapters/models/test_huggingface.py` mirrors `aef/adapters/models/huggingface.py`).
  - Use the `mock_chat` / `mock_judge` fixtures rather than constructing adapters by hand.
  - Use `MockChatScript(match=..., response=..., latency_ms=..., fail_with=...)` to exercise both happy paths and adapter-level failures.
  - Use `caplog_aef` to assert on logger output. Tests that assert on stderr text are flaky.
  - Use `pytest.mark.parametrize` to fan out a single behavior across inputs rather than copy-pasting.
- **Patterns to avoid**:
  - Do NOT use `unittest.mock.patch` to stub `httpx`, `transformers`, `openai`, or any other adapter dependency. Configure a `MockChatModel` instead.
  - Do NOT skip tests with `@pytest.mark.skipif(...)` for hardware reasons. Use one of the registered markers (`gpu`, `network`, `broker`, `docker`) so the gating is uniform.
  - Do NOT write tests that talk to the real internet without the `network` marker.
  - Do NOT call `time.sleep` in tests. Use `asyncio.sleep` with a frozen-time fixture or a `MockChatScript.latency_ms` value that the engine simulates.
  - Do NOT lower the coverage threshold per-PR to ship a feature. Add or improve tests instead.
- **Configuration**:
  - `[tool.pytest.ini_options]` registers markers explicitly: `markers = ["slow", "gpu", "network", "broker", "docker"]`.
  - Default `addopts` excludes the gated markers; CI workflows opt in for scheduled runs.
- **Migration steps**: none — greenfield.

### Verification

- [ ] `pyproject.toml` defines the five markers and enables `--strict-markers`.
- [ ] `pytest -q` (no extra args) runs only the un-gated tests and exits 0 on a clean tree.
- [ ] `pytest -q -m gpu` is empty until ADR-0013's smoke tests land; once they do, it runs only those.
- [ ] `MockChatModel` and `MockJudge` are present in the adapter registry by name.
- [ ] `MockChatModel` raises `MockChatModelError` (or equivalent) on an unmatched request — verifiable via a unit test.
- [ ] `mock_chat`, `mock_judge`, `tiny_dataset`, `in_memory_db`, `tmp_outputs`, `caplog_aef`, `local_engine` are documented fixtures available from `tests/conftest.py`.
- [ ] `pytest --cov=aef --cov-fail-under=85` succeeds against the un-gated suite.
- [ ] `rg "from unittest import mock" backend/tests` returns nothing on a clean tree (mocks come from the adapter layer, not `unittest.mock`).
- [ ] `rg "@patch\(" backend/tests` returns nothing on a clean tree.
- [ ] No test under `tests/` reaches the public internet without `@pytest.mark.network` (manual review + CI network sandboxing).
- [ ] Running `pytest --randomly-seed=last` after any failing run reproduces the failure (test order independence).

## Alternatives Considered

- **`unittest.mock.patch` everywhere**: rejected. Patching SDK internals couples tests to library implementation details. The mock adapters intercept at the project's own seam.
- **A separate "test mode" flag in real adapters**: rejected. Putting test logic in production adapters is exactly the coupling we want to avoid; the adapter registry pattern (ADR-0003) makes it unnecessary.
- **VCR / cassette-based recording of real model responses**: considered. Useful for cloud-API smoke tests, but ill-suited as the *primary* mocking strategy because cassettes drift silently when prompts change. Could be revisited as a supplemental tool inside `tests/smoke/cloud/` if needed.
- **Hypothesis-based property tests for metrics**: considered, and recommended as an *additive* tool inside `tests/unit/metrics/` rather than the default style. This ADR does not block its use.
- **No coverage gate**: rejected. A self-policing rule with no automation erodes. 85% is a deliberate floor, not a ceiling.

## More Information

- High-level architecture: [`../high_level_architecture.md`](../high_level_architecture.md) §9.4.
- External references:
  - [pytest documentation](https://docs.pytest.org/) — test runner, fixtures, markers, and `caplog`.
  - [pytest-cov documentation](https://pytest-cov.readthedocs.io/) — coverage integration.
  - [Hypothesis documentation](https://hypothesis.readthedocs.io/) — possible future property-based tests for contracts.
  - [FastAPI testing documentation](https://fastapi.tiangolo.com/tutorial/testing/) — API integration-test patterns.
  - [Playwright documentation](https://playwright.dev/) — frontend e2e test runner referenced by the frontend ADRs.
- Related ADRs:
  - [`0003-adapter-architecture-for-models-and-datasets.md`](0003-adapter-architecture-for-models-and-datasets.md) — defines the adapter registry that mocks plug into.
  - [`0010-code-quality-standards.md`](0010-code-quality-standards.md) — the same `uv run check` command runs `pytest` as a smoke marker.
  - [`0012-logging-and-telemetry-contract.md`](0012-logging-and-telemetry-contract.md) — `caplog_aef` is the canonical way to assert on log records.
  - [`0013-default-local-model-smollm.md`](0013-default-local-model-smollm.md) — the SmolLM smoke tests live under `tests/smoke/smollm/`, with GPU-only assertions behind the `gpu` marker.
  - [`0014-llm-as-judge-contract-and-bias-mitigation.md`](0014-llm-as-judge-contract-and-bias-mitigation.md) — LLM-as-judge tests rely on `MockJudge` exclusively in default CI.
- Revisit triggers:
  - The `MockChatScript` matching model becomes too verbose for common test patterns — extend `MockMatch` rather than introducing ad-hoc patching.
  - Coverage stabilizes consistently above 90% — raise the gate.
  - A class of bugs slips past mock-driven tests because mocks paper over a real-adapter behavior — add a contract test that runs the same scenario against `MockChatModel` and a real adapter under the appropriate marker.
