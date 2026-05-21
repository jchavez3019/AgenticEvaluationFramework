---
status: proposed
date: 2026-05-17
decision-makers: jorgejc2
---

# Adapter Architecture for Models and Datasets

## Context and Problem Statement

The framework must call into four very different model surfaces — Hugging Face local models, Ollama models, cloud LLM APIs (OpenAI, Anthropic, etc.), and LangGraph agentic graphs — and ingest evaluation datasets from at least two sources today (Hugging Face Hub and local CSV files), with more formats expected (JSON, SQL, parquet, etc.). It must also accept user-defined models, graphs, and datasets without requiring changes to the core code.

Without a uniform contract for these external surfaces, the engine, metrics, persistence, and API would each grow conditional logic ("if this is Ollama, then..."). That coupling is the single biggest extensibility risk in the framework. Every new runtime would touch the engine, metrics, and persistence layers, and adding a custom user model would require forking the project.

We need an adapter pattern that:

- Is genuinely typed end-to-end. The engine should be able to schedule work, batch requests, and persist results without ever inspecting an adapter's internals.
- Makes new adapters a self-contained additive change — one new file plus a registry entry.
- Lets configs select an adapter by string identifier (so YAML/Hydra configs can pick `huggingface:smollm-1.7b` or `dataset:csv:./data/eval.csv`).
- Supports first-class **mock** adapters used in unit tests, fixtures, and offline development, with the same code path as real adapters.

The high-level architecture document (`../high_level_architecture.md` §3.2) sketches this design. This ADR locks it in as a binding contract for all future code.

## Decision

Adopt a **Protocol-based, registry-driven adapter architecture** with three concrete adapter families, each defined by a typed `Protocol` plus a Pydantic spec model.

### Adapter families

1. **`ModelAdapter`** — wraps a generation surface (LLM, chat model, agentic graph). Returns text in response to a `GenerationRequest`.
2. **`DatasetAdapter`** — produces a stream of `EvaluationSample` rows from some external source.
3. **`JudgeAdapter`** — a specialization of `ModelAdapter` whose outputs conform to a structured rubric schema, used by LLM-as-judge metrics. Treated as a `ModelAdapter` by the engine, but with extra schema constraints enforced by the metric layer.

(`StorageAdapter` exists too, but its decision is owned by the persistence ADR `0006`. The pattern is the same.)

### Contract shape

Each adapter family has:

- A `Protocol` (or `abc.ABC`) defining its async methods.
- A Pydantic **spec model** (`ModelAdapterSpec`, `DatasetAdapterSpec`) describing the adapter's identity, configuration, and declared capabilities. The spec is what gets serialized into `EvaluationRunRequest` and stored alongside every run for reproducibility.
- A central **registry** keyed by string identifier. Concrete adapters register themselves at import time (or lazily via entry points) so configs can refer to them by name.

Skeleton (illustrative; not the final code, but binding on the shape):

```python
class ModelAdapter(Protocol):
    spec: ModelAdapterSpec

    async def generate(self, request: GenerationRequest) -> GenerationResponse: ...
    async def close(self) -> None: ...


class DatasetAdapter(Protocol):
    spec: DatasetAdapterSpec

    async def load(self) -> AsyncIterator[EvaluationSample]: ...
    async def __aenter__(self) -> "DatasetAdapter": ...
    async def __aexit__(self, *exc_info: object) -> None: ...
```

### Registry

A single registry module (`aef.adapters.registry`) exposes:

- `register_model_adapter(name: str, factory: Callable[[ModelAdapterSpec], ModelAdapter])` and the analogous `register_dataset_adapter`.
- `build_model_adapter(spec: ModelAdapterSpec) -> ModelAdapter` and `build_dataset_adapter(spec: DatasetAdapterSpec) -> DatasetAdapter`.
- A discovery hook for entry-point-based plugins so third-party packages can ship adapters without modifying this repo.

### Capability declarations

Every `ModelAdapterSpec` exposes a typed `capabilities` sub-model with explicit fields, including but not limited to:

- `supports_streaming: bool`
- `supports_tool_use: bool`
- `max_context_tokens: int | None` — total prompt + completion limit imposed by the model. The engine refuses any request whose declared input-token count plus `GenerationConfig.max_output_tokens` would exceed this.
- `requires_gpu: bool`
- `is_remote: bool` (cloud API vs local)
- `cost_reporting: Literal["full", "tokens-only", "none"]`
- `supported_sampling_parameters: frozenset[SamplingParameter]` — the set of `GenerationConfig` fields the adapter actually honors at runtime. Discussed below.

The engine consults these capabilities to decide scheduling (which worker pool, whether to micro-batch, whether to enforce a rate limit) and to validate generation configs before dispatching them.

### Generation configuration (sampling parameters)

Generation parameters are a first-class, runtime-configurable part of the request contract — not adapter-specific kwargs. Any user (CLI, frontend, library caller) must be able to override them per run when the underlying model exposes them.

The framework defines a single `GenerationConfig` Pydantic model, attached to `GenerationRequest`:

```python
SamplingParameter = Literal[
    "temperature",
    "top_k",
    "top_p",
    "repetition_penalty",
    "max_output_tokens",
    "seed",
]


class GenerationConfig(BaseModel):
    """Runtime-configurable generation parameters.

    Every field is optional. ``None`` means "use the adapter / model default".
    Adapters MUST honor every field that appears in their
    ``capabilities.supported_sampling_parameters`` set, and MUST raise
    ``UnsupportedSamplingParameterError`` (defined below) when an explicitly-set
    field is not in that set.
    """

    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_k: int | None = Field(default=None, ge=1)
    top_p: float | None = Field(default=None, gt=0.0, le=1.0)
    repetition_penalty: float | None = Field(default=None, gt=0.0)
    max_output_tokens: int | None = Field(default=None, ge=1)
    seed: int | None = Field(default=None, ge=0)


class GenerationRequest(BaseModel):
    messages: list[ChatMessage] # assuming chat-shaped adapters
    sampling: GenerationConfig = Field(default_factory=GenerationConfig)
```

Behavior:

- An adapter declares which sampling parameters it implements via `capabilities.supported_sampling_parameters`. For example, the Hugging Face adapter advertises all six; the OpenAI chat-completions adapter advertises `temperature`, `top_p`, `max_output_tokens`, `seed` (no `top_k`, no `repetition_penalty` — chat-completions exposes `frequency_penalty` / `presence_penalty` which are _different_ knobs and would belong on a future extension).
- If a user explicitly sets a parameter (i.e., not `None`) that is not in the adapter's supported set, the adapter raises `UnsupportedSamplingParameterError` _during request construction_, before any side-effecting model call. This is intentionally strict: silently dropping a parameter would mislead the user about what the model actually saw.
- The engine validates `prompt_tokens + (sampling.max_output_tokens or 0) ≤ capabilities.max_context_tokens` before dispatch. Overflow raises `ContextOverflowError`. Token counting uses the adapter's tokenizer when available; otherwise the adapter declares `max_context_tokens=None` and the validation is skipped (with a single-line warning at run start, not per sample).
- `GenerationConfig` is serialized verbatim into `EvaluationRunResult.run_request.generation_config` and into the persisted `runs.model_spec` JSON. Reproducibility is binding: re-running the same `EvaluationRunRequest` against a deterministic adapter (e.g., `MockChatModel`, or an HF model with the same `seed`) produces byte-identical generations.

Future extensions (e.g., `frequency_penalty`, `presence_penalty`, stop sequences, response-schema constraints) follow the same pattern: add the field as `Optional`, extend `SamplingParameter`, and have each adapter advertise support explicitly. The set is closed and typed; no `Dict[str, Any]` for "extra" knobs.

### Required adapters at v1

The following ship in `aef.adapters.models`:

- `huggingface` — local Hugging Face Transformers models. Used by the SmolLM smoke-test path (ADR-0013).
- `ollama` — Ollama HTTP-bound local models.
- `openai` — representative cloud chat-completions adapter.
- `langgraph` — wraps a compiled LangGraph graph as a `ModelAdapter`. Internal trace data (per high-level architecture §11.4) is captured as a structured sub-model on `GenerationResponse`.
- `mock-chat` (`MockChatModel`) — deterministic adapter for tests and offline development.
- `mock-judge` (`MockJudge`) — deterministic judge adapter for LLM-as-judge metric tests.

The following ship in `aef.adapters.datasets`:

- `huggingface` — Hugging Face Hub datasets.
- `csv` — local CSV files.
- `mock` — deterministic in-memory dataset for tests.

### Non-goals

- We are NOT defining how individual metrics are registered here. That belongs to the metric-suite ADR (`0004`).
- We are NOT specifying the storage adapter contract here. That belongs to the persistence ADR (`0006`).
- We are NOT supporting synchronous adapter methods. All adapter calls are `async`. Sync wrappers can be added later if a real need emerges.
- We are NOT exposing model internals (logits, hidden states) through `ModelAdapter`. The framework treats every model as a text-in/text-out surface.
- We are NOT supporting "extra" untyped sampling parameters via a generic dictionary. Every supported knob is an explicit, validated field on `GenerationConfig`. Adapter-specific extensions go through new typed fields, not free-form kwargs.

## Consequences

- Good, because adding a new model runtime or dataset format is a strictly additive change: one new file in the appropriate adapter directory, plus a registry call. No edits to the engine, metrics, or persistence layers.
- Good, because the engine schedules work against a single typed contract regardless of what's behind it. A future `RayEngine` (per high-level architecture §7.4) inherits this for free.
- Good, because mock adapters are first-class members of the same registry, which means mock-driven tests exercise the exact code path real adapters exercise.
- Good, because `EvaluationRunRequest` is fully serializable: an adapter spec is just data, so a run config can be saved to disk, replayed, or rendered in the dashboard.
- Bad, because contributors writing a new adapter have to fill out the full Pydantic spec (capabilities, cost reporting, etc.) even when they only care about basic generation. We accept this friction; the alternative is silent capability mismatches at runtime.
- Bad, because Python's `Protocol` does not enforce method existence at import time; mistakes surface only at first use. We mitigate this with Pyright strict mode (per ADR-0010) running in CI and with adapter-shape unit tests in `tests/unit/adapters/`.
- Neutral, because the registry adds a small layer of indirection. The benefit (config-driven adapter selection) clearly outweighs the cost.

## Implementation Plan

- **Affected paths**:
  - `backend/src/aef/contracts/adapter_spec.py` — `ModelAdapterSpec`, `DatasetAdapterSpec`, `ModelCapabilities`, `JudgeAdapterSpec`.
  - `backend/src/aef/contracts/run.py` — `GenerationRequest`, `GenerationResponse`, `EvaluationSample`, `EvaluationRunRequest`, `EvaluationRunResult`.
  - `backend/src/aef/adapters/registry.py` — registry, factory functions, entry-point discovery.
  - `backend/src/aef/adapters/models/base.py` — `ModelAdapter` Protocol.
  - `backend/src/aef/adapters/models/huggingface.py` — Hugging Face local adapter (depends on `transformers` optional group).
  - `backend/src/aef/adapters/models/ollama.py` — Ollama HTTP adapter.
  - `backend/src/aef/adapters/models/openai.py` — cloud chat-completions adapter (depends on `openai` optional group).
  - `backend/src/aef/adapters/models/langgraph.py` — LangGraph wrapper that captures internal trace events on `GenerationResponse.trace`.
  - `backend/src/aef/adapters/models/mocks.py` — `MockChatModel` and `MockJudge`.
  - `backend/src/aef/adapters/datasets/base.py` — `DatasetAdapter` Protocol.
  - `backend/src/aef/adapters/datasets/huggingface.py`, `csv.py`, `mocks.py`.
  - `backend/tests/unit/adapters/` — shape tests asserting that every registered adapter satisfies its Protocol and that its spec round-trips through Pydantic.
- **Dependencies**:
  - `transformers`, `torch`, `accelerate` — optional group `models-hf`.
  - `ollama` (Python client) — optional group `models-ollama`.
  - `openai` and/or `anthropic` — optional groups `models-openai`, `models-anthropic`.
  - `langgraph` — optional group `models-langgraph`.
  - `datasets` (Hugging Face) — optional group `datasets-hf`.
  - The mock adapters and base contracts have NO third-party dependencies beyond Pydantic. This guarantees that `pytest tests/unit/` can run with the minimal install set.
- **Patterns to follow**:
  - All adapter classes are `async`. Synchronous third-party SDKs are wrapped via `asyncio.to_thread` inside the adapter, never exposed.
  - Every adapter's `spec` is constructed and validated by Pydantic before any side-effecting call. If the spec is invalid, the adapter must raise during construction, never silently degrade.
  - Adapter modules import their third-party dependency lazily (`import torch` inside `__init__` or even inside `generate`) so that `aef.adapters.models` can be imported without every optional group installed.
  - Registry entries are made at the bottom of each adapter module via `register_model_adapter("<name>", _factory)`. The package's `__init__.py` imports the modules so registration happens at package import.
  - Capabilities are populated explicitly on the spec; do not infer them at runtime.
- **Patterns to avoid**:
  - Do NOT pass plain dictionaries or `kwargs` between adapters and the engine. Every shape is a Pydantic model.
  - Do NOT add adapter-specific branches to the engine, metrics, or persistence code. Anything an adapter needs to advertise lives on its `spec.capabilities`.
  - Do NOT subclass `ModelAdapter` to add framework-specific methods (e.g., a public `tokenize` method). If a metric needs structured per-token info, define a new Protocol or extend `GenerationResponse` instead.
  - Do NOT import an optional dependency at module top level in a base adapter file. All heavyweight imports are deferred.
- **Configuration**:
  - Adapter selection in YAML / Hydra configs is by string identifier: `model.kind: "huggingface"`, `model.spec.model_id: "HuggingFaceTB/SmolLM2-135M-Instruct"`. The CLI ADR (`0007`) details the config schema.
  - Optional dependency groups are declared in `pyproject.toml`. Users install with `uv sync --extra models-hf --extra datasets-hf`, etc.
- **Migration steps**: none — this is greenfield.

### Verification

- [ ] `aef.adapters.models.base.ModelAdapter` and `aef.adapters.datasets.base.DatasetAdapter` exist as `Protocol` definitions.
- [ ] `aef.contracts.adapter_spec` defines `ModelAdapterSpec`, `DatasetAdapterSpec`, `ModelCapabilities`, `JudgeAdapterSpec`, all as Pydantic v2 models with no `Dict[str, Any]` fields on public surfaces.
- [ ] `aef.adapters.registry` exposes `register_model_adapter`, `register_dataset_adapter`, `build_model_adapter`, `build_dataset_adapter`.
- [ ] At least the following names are present in the registry after `import aef.adapters`: `huggingface`, `ollama`, `openai`, `langgraph`, `mock-chat`, `mock-judge` (model adapters); `huggingface`, `csv`, `mock` (dataset adapters).
- [ ] `MockChatModel` and `MockJudge` can be constructed without any optional dependency group installed.
- [ ] Importing `aef.adapters.models.huggingface` does not require `transformers` to be installed unless the adapter is actually instantiated.
- [ ] `ModelAdapterSpec` round-trips through `model_dump()` and `model_validate()` without information loss for every adapter that ships in v1.
- [ ] Unit tests in `tests/unit/adapters/` assert that every registered adapter satisfies its Protocol and that its capabilities sub-model has every required field populated (no defaults silently masking missing data).
- [ ] Engine, metric, and persistence code contain zero `isinstance(adapter, X)` branches against concrete adapter classes.
- [ ] `GenerationConfig` is defined exactly as in this ADR (six optional fields with the documented validators) and is exported from `aef.contracts.run`.
- [ ] Each shipped `ModelAdapter` declares `capabilities.supported_sampling_parameters` as a non-empty `frozenset[SamplingParameter]` (or empty if the adapter genuinely supports no sampling knobs, but that must be intentional and documented).
- [ ] Setting a `GenerationConfig` field that is not in the adapter's supported set raises `UnsupportedSamplingParameterError` before any model call.
- [ ] When `capabilities.max_context_tokens` is set, the engine refuses dispatch with `ContextOverflowError` if `prompt_tokens + (sampling.max_output_tokens or 0)` exceeds it.
- [ ] `EvaluationRunResult.run_request.generation_config` round-trips through Pydantic serialization with the same field set and values that the user supplied.

## Alternatives Considered

- **Single `LLM` ABC for all model surfaces**: rejected. ABCs are heavier than Protocols and force inheritance even for thin third-party wrappers. Protocols fit duck-typed adapters better and integrate cleanly with Pyright (per ADR-0010).
- **Use LangChain's `BaseLanguageModel` directly**: rejected. It would lock the framework to LangChain's lifecycle and runtime semantics for every adapter, including ones that have nothing to do with LangChain (Ollama, raw HF). LangChain models can still be wrapped behind our `ModelAdapter` if a user wants that.
- **Plugin discovery via entry points only (no in-tree adapters)**: rejected. We want first-party, in-tree adapters for the four runtimes named in the architecture doc to keep the smoke-test path tight. Entry-point discovery is added on top for third-party adapters.
- **A single `Adapter` protocol covering models, datasets, and storage**: rejected. The methods, lifecycles, and concerns are different enough that a unified protocol would be either uselessly broad (`run(input) -> output`) or full of optional methods. Three small Protocols are cleaner.
- **Generic dictionary-based adapter configs**: rejected outright by the strict-typing rule (high-level architecture §9.1). Adapter configs are Pydantic models, full stop.

## More Information

- High-level architecture: [`../high_level_architecture.md`](../high_level_architecture.md) §3.2, §11.4.
- External references:
  - [Python `typing.Protocol` documentation](https://docs.python.org/3/library/typing.html#typing.Protocol) — structural typing mechanism used for adapters.
  - [Pydantic documentation](https://docs.pydantic.dev/latest/) — typed specs and validation.
  - [Hugging Face Transformers documentation](https://huggingface.co/docs/transformers/index) — local HF model adapter surface.
  - [Ollama API documentation](https://github.com/ollama/ollama/blob/main/docs/api.md) — Ollama adapter surface.
  - [LangGraph documentation](https://langchain-ai.github.io/langgraph/) — graph adapter target.
  - [Hugging Face Datasets documentation](https://huggingface.co/docs/datasets/index) — dataset adapter target.
- Related ADRs:
  - `0002-backend-technology-stack.md` — Pydantic v2 and async runtime are prerequisites.
  - [`0004-default-metric-suite-and-plugin-contract.md`](0004-default-metric-suite-and-plugin-contract.md) — metric registry follows the same registry pattern but is owned separately.
  - [`0006-persistence-sqlite-default-postgres-swap-in.md`](0006-persistence-sqlite-default-postgres-swap-in.md) — `StorageAdapter` follows the same pattern.
  - [`0011-testing-strategy-and-mock-adapters.md`](0011-testing-strategy-and-mock-adapters.md) — testing strategy formalizes the mock-adapter expectations stated here.
  - [`0014-llm-as-judge-contract-and-bias-mitigation.md`](0014-llm-as-judge-contract-and-bias-mitigation.md) — LLM-as-judge contract specializes `ModelAdapter` into `JudgeAdapter`.
- Revisit triggers:
  - A new adapter family appears that does not fit any of model / dataset / judge / storage (e.g., a "tool" adapter for evaluating tool-use behavior). Consider whether to extend or split.
  - A real third-party use case requires synchronous adapter methods. Consider adding a sync subset.
