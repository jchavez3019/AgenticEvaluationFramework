---
status: proposed
date: 2026-05-18
decision-makers: jorgejc2
---

# Default Metric Suite and Metric-Plugin Contract

## Context and Problem Statement

The whole point of the framework is to evaluate model outputs against references. The high-level architecture document (§8) commits to an opinionated default suite spanning lexical, embedding-based, learned (LLM-as-judge), conditionally RAG-aware, and operational metrics. It also commits to making metrics extensible — users must be able to register their own metric without forking the codebase.

Without a binding metric contract, every metric implementation invents its own input/output shape, the registry diverges from the model/dataset adapter pattern, and "what does this metric actually measure" becomes folklore. A few specific risks:

- Metric values get coerced into untyped dicts, so the dashboard cannot render them uniformly and the persistence layer (ADR-0006) cannot round-trip them safely.
- Per-sample metric latency is not recorded, so the telemetry block in `EvaluationRunResult` (ADR-0012) has gaps for the most variable phase of the run.
- Mock-driven testing of metrics (ADR-0011) becomes ad-hoc because the metric Protocol does not exist.
- LLM-as-judge metrics, which sit at the boundary between "metric" and "model", get implemented inconsistently across the codebase.

This ADR locks in:

1. The `Metric` Protocol and its registry.
2. The `MetricResult` schema and how variadic metrics (per-class breakdowns, multi-score outputs) avoid `Dict[str, Any]`.
3. The v1 default metric suite — exactly which metrics ship and in which categories.
4. The conditional gating for RAG-aware metrics.
5. The plugin discovery story for user-defined metrics.

ADR-0014 specializes the LLM-as-judge family further; this ADR fixes the contract that ADR-0014 then implements.

## Decision Drivers

- **Strict typing on all metric values.** `Dict[str, Any]` is forbidden everywhere else; metrics are no exception.
- **Determinism in tests.** The mock-driven test suite (ADR-0011) requires that metric outputs are reproducible given seeded inputs.
- **Persistence-friendliness.** Metric results must round-trip through SQLite (ADR-0006) without information loss.
- **Conditional applicability.** Some metrics (RAG, structured-output validity) only run when the dataset/adapter exposes the right shape. The metric layer must opt-out cleanly rather than failing or fabricating.
- **Extensibility parity with adapters.** Adding a metric should look like adding a model adapter (ADR-0003): one new file plus a registry entry.

## Considered Options

There is one realistic option for the contract shape itself (a Protocol + registry, mirroring ADR-0003), so this ADR uses the simple template format and uses MADR-style sub-arguments only inside the *suite* selection (which metrics to ship in v1).

Considered but rejected: an inheritance-based `BaseMetric` class hierarchy. Rationale in Alternatives Considered.

## Decision

Adopt a **Protocol-based, registry-driven metric architecture** that mirrors the adapter architecture in ADR-0003, plus a fixed v1 default metric suite. ADR-0014 specializes the LLM-as-judge slice.

### 1. The `Metric` Protocol

```python
class MetricKind(StrEnum):
    LEXICAL = "lexical"
    EMBEDDING = "embedding"
    LEARNED = "learned"          # LLM-as-judge family — see ADR-0014
    RAG = "rag"                  # conditional; gated by dataset/adapter capability
    OPERATIONAL = "operational"  # latency, tokens, cost, validity


class MetricInputs(BaseModel):
    """Per-sample inputs visible to a metric.

    Optional fields are populated only when the dataset/adapter provides them.
    Metrics declare what they require via ``Metric.spec.required_inputs``.
    """
    input: str
    candidate: str                       # the model's generation
    reference: str | None = None         # gold reference (if dataset provides one)
    references: list[str] | None = None  # multi-reference variant
    context: list[RetrievedChunk] | None = None  # RAG context (when present)
    gold_context: list[RetrievedChunk] | None = None  # RAG gold (when present)
    sample_metadata: SampleMetadata | None = None    # typed sub-model, never dict


class Metric(Protocol):
    spec: MetricSpec  # Pydantic; identity, kind, required inputs, capabilities

    async def compute(
        self, inputs: MetricInputs
    ) -> MetricResult: ...

    async def compute_batch(
        self, inputs: list[MetricInputs]
    ) -> list[MetricResult]:
        """Optional override; default implementation maps ``compute``."""
        ...

    async def aggregate(
        self, per_sample: list[MetricResult]
    ) -> MetricResult:
        """Run-level summary. Most metrics return mean ± stddev; some (e.g.,
        Self-BLEU) compute a fundamentally run-level value here."""
        ...

    async def close(self) -> None: ...
```

`MetricSpec` carries:

- `name: str` — registry key.
- `kind: MetricKind` — pool-routing hint for the engine (per ADR-0005).
- `version: str` — semver. Stored on `MetricResult` so persistence is reproducible across upgrades.
- `required_inputs: frozenset[Literal["reference", "references", "context", "gold_context"]]` — declarative. The engine validates the dataset row provides what each metric needs *before* dispatching the run, refusing with a clear error if not. RAG metrics declare `"context"` (and optionally `"gold_context"`); answer-relevancy declares no references at all; BLEU declares `"reference"` or `"references"`.
- `requires_gpu: bool` — embedding metrics with large encoders, BERTScore, learned metrics may set this.
- `is_remote: bool` — true for cloud judges (the metric layer reuses the same adapter capability semantics as ADR-0003).
- `cost_reporting: Literal["full", "tokens-only", "none"]`.
- `applicable_when: MetricApplicability` — a small Pydantic model with Boolean predicates (`requires_reference: bool`, `requires_context: bool`) that the engine evaluates per-sample. A sample that does not match a metric's `applicable_when` produces a `MetricResult` with `status="skipped"` rather than `"error"`.

### 2. `MetricResult` — typed, variadic-safe

```python
class MetricStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    SKIPPED = "skipped"  # not applicable to this sample (e.g., RAG without context)


class SubScore(BaseModel):
    """A single named sub-value emitted by a variadic metric."""
    name: str
    value: float
    notes: str | None = None


class MetricResult(BaseModel):
    metric_name: str
    metric_version: str
    sample_idx: int | None  # None for run-level (aggregate) results
    status: MetricStatus
    value: float | None       # primary scalar; None when the metric is purely structured
    sub_values: list[SubScore]  # for per-class breakdowns, multi-score outputs
    compute_latency_ms: float
    exception_class: str | None = None
    exception_message: str | None = None
```

This contract gives every metric the same persistable shape:

- A single primary scalar lives in `value` for the dashboard's quick-look columns.
- Multi-valued metrics (ROUGE-1/2/L/Lsum, BERTScore P/R/F1) use `sub_values: list[SubScore]` — a typed, structured list, *not* `Dict[str, Any]`.
- Skipped samples carry `status="skipped"` and `value=None`. Aggregations skip them automatically.
- Per-sample compute latency feeds the run's `TelemetryReport` (ADR-0012).

### 3. Registry and discovery

A `MetricRegistry` mirrors the adapter registry from ADR-0003:

- `register_metric(name: str, factory: Callable[[MetricSpec], Metric])` and `build_metric(spec: MetricSpec) -> Metric`.
- All in-tree v1 metrics are registered at module import via the `metrics/__init__.py` chain.
- Third-party metrics use the `aef.metrics` Python entry-point group; `MetricRegistry` discovers them lazily at first lookup.
- Selection in YAML / Hydra (per ADR-0007) is by name: `metrics: [{ name: "rouge", config: { variants: ["1", "2", "L"] } }, ...]`.

### 4. The v1 default metric suite

The shipped suite, by category. Each metric has an entry in `aef.metrics.<category>.<module>` and is registered by name.

#### Lexical (`aef.metrics.lexical`)

| Name           | What it does                                                       | Source library                | `value` semantics            |
| -------------- | ------------------------------------------------------------------ | ----------------------------- | ---------------------------- |
| `bleu`         | Modified n-gram precision with brevity penalty                     | `sacrebleu>=2.4`              | corpus BLEU (0-100)          |
| `rouge`        | ROUGE-1 / ROUGE-2 / ROUGE-L / ROUGE-Lsum                           | `rouge-score>=0.1.2`          | F1 of the configured variant; sub_values: each variant's P/R/F |
| `ngram_overlap`| Configurable n-gram precision/recall/F1                            | in-tree (~80 LOC)             | F1                            |
| `chrf`         | Character n-gram F-score (chrF / chrF++)                           | `sacrebleu`                   | chrF++ score                  |
| `meteor`       | Stemming + synonym-aware n-gram alignment                          | `nltk` METEOR                 | METEOR score (0-1)            |
| `exact_match`  | Strict string equality after configurable normalization            | in-tree                       | 1.0 / 0.0                     |
| `token_f1`     | SQuAD-style token-level F1 (set-based)                             | in-tree                       | F1                            |
| `fuzzy_match`  | Levenshtein / token-set ratio                                      | `rapidfuzz>=3.9`              | 0-1 ratio                     |

All lexical metrics declare `kind=LEXICAL`, `requires_gpu=False`, `is_remote=False`. They run on `local_cpu` workers (per ADR-0005).

#### Embedding (`aef.metrics.embedding`)

| Name             | What it does                                                                   | Source library                                        |
| ---------------- | ------------------------------------------------------------------------------ | ----------------------------------------------------- |
| `semantic_sim`   | Cosine similarity over Sentence-Transformers embeddings                        | `sentence-transformers>=3` (default `all-MiniLM-L6-v2`)|
| `bertscore`      | BERTScore precision / recall / F1                                              | `bert-score>=0.3.13`                                  |

Embedding metrics declare `kind=EMBEDDING`. The metric's `MetricSpec.requires_gpu` is a static declaration: metrics that *require* a GPU set `True`; metrics with a viable CPU fallback set `False` and choose their runtime device dynamically at first `compute(...)` call based on `torch.cuda.is_available()`. The engine routes `requires_gpu=True` metrics to `local_gpu` and `requires_gpu=False` metrics to `local_cpu` (per ADR-0005's pool routing). For v1, both default embedding metrics (`semantic_sim`, `bertscore`) ship with `requires_gpu=False` and choose CPU vs CUDA at runtime; users who want forced GPU routing override `requires_gpu=True` in the metric config. The default embedding model is configurable per metric.

#### Learned / LLM-as-judge (`aef.metrics.learned`) — see ADR-0014 for the full contract

| Name              | What it does                                                                |
| ----------------- | --------------------------------------------------------------------------- |
| `llm_judge`       | Single-answer rubric scoring via a `JudgeAdapter`                           |
| `pairwise_judge`  | A/B preference judging (compare two candidates against the same input)      |
| `g_eval`          | Multi-step CoT structured judging using the same `RubricScore` schema       |

These declare `kind=LEARNED`. Routing depends on the underlying judge adapter: `is_remote=True` ⇒ `cloud_judge_api`; `is_remote=False` and `requires_gpu=True` ⇒ `local_gpu` (judge pool, distinct from the main generation pool). ADR-0014 specifies the judge adapter contract, versioned Jinja-2 prompt templates with bias-anchor includes, deterministic seeding (`temperature=0` + fixed `seed`), and the `BiasMitigation` defaults (position-swap for pairwise, length / style / self-preference anchors, parser retries on bad JSON).

#### RAG-aware (`aef.metrics.rag`) — conditional

These metrics declare `applicable_when.requires_context=True`. They are skipped (with `status="skipped"`) on samples that do not provide retrieved context, rather than failing the run.

These metrics are **end-to-end, externally supplied-context metrics**. They cover the case where the dataset row already contains the query, the retrieved documents/chunks that were provided to the model or graph, and optionally gold retrieval labels / golden chunks. The framework then asks: given the text output and the externally visible retrieval payload, was the answer faithful to those chunks, and were the supplied chunks relevant?

They do **not** inspect or instrument the underlying model/graph's internal retriever, vector store, reranker, tool calls, hidden chain state, or private RAG traces. If a LangGraph adapter or dataset explicitly exposes retrieval traces as part of its text-in/text-out contract, those traces can be evaluated. Otherwise the framework treats the model/graph as a black box and does not try to break into its internal RAG components.

| Name                  | What it does                                                                                                | Notes                                          |
| --------------------- | ----------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| `faithfulness`        | NLI-based or judge-based: does the candidate entail from the supplied context?                              | Two implementations: `nli` and `judge`.        |
| `answer_relevancy`    | Semantic match between the input question and the candidate answer                                          | Embedding-backed.                              |
| `context_precision`   | Of retrieved chunks, what fraction are relevant?                                                            | Requires `gold_context`.                       |
| `context_recall`      | Of relevant chunks, what fraction were retrieved?                                                           | Requires `gold_context`.                       |
| `retrieval_ranking`   | Recall@k, MRR, nDCG when `gold_context` includes per-chunk relevance labels                                 | Sub-values: one per ranking statistic.         |

If neither `context` nor `gold_context` is present, these metrics are unavailable (filtered from the resolved run *before* execution starts) with a clear message, not skipped per-sample. This avoids running an entire metric just to mark every sample skipped.

#### Operational (`aef.metrics.operational`) — always-on, free

These run alongside generation and consume no extra model calls.

| Name                  | What it does                                                                                |
| --------------------- | ------------------------------------------------------------------------------------------- |
| `latency`             | Per-sample generation latency, reported as `value`; sub_values: p50, p95, p99 at run level. |
| `token_counts`        | Prompt / completion / total token counts; sub_values for each.                              |
| `cost`                | USD per sample / per run, when the adapter reports it; null when not available.             |
| `output_validity`     | JSON parse success rate, when the adapter declares structured output. Skipped otherwise.    |

Operational metrics are populated from `GenerationResponse` fields (per ADR-0003) and do not require a separate compute pass. They are the only metrics whose *value sources* are not the candidate text itself but the run's telemetry.

### 5. Suggested metrics deferred to v1.x (placeholders, not shipped)

These match `high_level_architecture.md` §8.2 and are intentionally out of scope for v1. They will be added behind their own ADR or as additive entries:

- `toxicity` (Detoxify or a `safety-judge`).
- `pii_detection` (regex + NER + Presidio-style; see ADR-0014's bias section for similar prompt-anchoring concerns).
- `hallucination_nli` (NLI-based, distinct from `faithfulness` because it does not require retrieved context).
- `calibration` (correlate adapter-reported confidence with correctness).
- `diversity` (Self-BLEU, distinct-n).

### 6. Validation timing

The engine performs all metric/dataset/adapter validation *before* dispatching any work:

- For each requested metric, `MetricSpec.required_inputs` is intersected with what the dataset adapter declares it provides. Missing inputs short-circuit with `MissingMetricInputError(metric=…, missing=…)`.
- For each metric whose `applicable_when` is statically incompatible with the dataset, the metric is removed from the run with a single log line at start. Per-sample skipping is reserved for metrics whose applicability is sample-dependent (e.g., RAG faithfulness on a dataset where some rows have context and others do not).
- The CLI's `validate_config` step (per ADR-0007) runs all of the above before any model is loaded.

### Non-goals

- We are NOT shipping toxicity, PII, hallucination-NLI, calibration, or diversity metrics in v1. See §5 above.
- We are NOT supporting metric *chains* in v1 (e.g., "feed BERTScore output into LLM-as-judge"). Each metric stands alone; composition is the user's responsibility.
- We are NOT exposing metric-internal state (intermediate scores, per-token weights) on `MetricResult`. The structured `sub_values: list[SubScore]` is the only escape hatch, and it is for *named* sub-scores.
- We are NOT defining a metric *interpretation* layer. The dashboard renders raw values; explanatory commentary lives in the Knowledge Base ("Blog") section of the frontend (per high-level architecture §5.3).
- We are NOT exposing untyped extras via `Dict[str, Any]`. New metric outputs add typed fields or registered `SubScore` entries.

## Consequences

- Good, because the metric contract is a strict mirror of the adapter contract (ADR-0003): the same engine, the same registry pattern, the same Pydantic spec story. Future contributors learn one shape, not two.
- Good, because `MetricResult.value` plus `sub_values` covers both scalar and variadic outputs without ever resorting to untyped dicts.
- Good, because conditional metrics (RAG family) are gated by typed `applicable_when` predicates, so they cannot produce false data on inapplicable samples.
- Good, because per-sample `compute_latency_ms` makes the metric phase visible in the telemetry block, which is what the dashboard's run-comparison view needs to surface "metric X dominates the run latency".
- Good, because the v1 suite covers the four canonical families (lexical / embedding / learned / RAG) plus operational concerns. A user who wants more either turns on the v1.x suggestions when they ship, or adds their own metric via the registry.
- Bad, because shipping a broad suite means tracking a broad set of upstream libraries (`sacrebleu`, `rouge-score`, `nltk`, `rapidfuzz`, `sentence-transformers`, `bert-score`). Each is pinned and gated behind an optional dependency group.
- Bad, because some metrics (BERTScore, embedding-based) carry a multi-hundred-MB model download on first use. Mitigation: each metric's `Metric` exposes a `warmup()` that tests can call inside fixtures; CI uses a tiny test-tier embedding model (`sentence-transformers/all-MiniLM-L6-v2` 80 MB) under `MockChatModel` paths.
- Bad, because the per-metric optional dependency groups multiply the install matrix. We accept that — running `uv sync` with no extras still gets a working framework with mock adapters and the lexical metric subset that has zero heavy deps.
- Neutral, because the Python entry-point plugin discovery for third-party metrics is lazy. A user who never defines a custom metric never pays the discovery cost.

## Implementation Plan

- **Affected paths**:
  - `backend/src/aef/metrics/__init__.py` — re-exports `Metric`, `MetricResult`, `MetricInputs`, `MetricRegistry`, `MetricKind`, `MetricStatus`, `SubScore`.
  - `backend/src/aef/metrics/base.py` — `Metric` Protocol, `MetricSpec`, `MetricInputs`, `MetricResult`, `MetricApplicability`, `SubScore`.
  - `backend/src/aef/metrics/registry.py` — `MetricRegistry`, factory functions, entry-point discovery.
  - `backend/src/aef/metrics/lexical/{bleu,rouge,ngram,chrf,meteor,exact_match,token_f1,fuzzy_match}.py`.
  - `backend/src/aef/metrics/embedding/{semantic_sim,bertscore}.py`.
  - `backend/src/aef/metrics/learned/{llm_judge,pairwise_judge,g_eval}.py` (specialized further by ADR-0014).
  - `backend/src/aef/metrics/rag/{faithfulness,answer_relevancy,context_precision,context_recall,retrieval_ranking}.py`.
  - `backend/src/aef/metrics/operational/{latency,token_counts,cost,output_validity}.py`.
  - `backend/src/aef/contracts/run.py` — already references metrics; extends `EvaluationRunResult.metric_results: list[MetricResult]` and `EvaluationRunResult.run_request.metrics: list[MetricSpec]`.
  - `configs/metrics/{default,lexical_only,embedding_only,judge_only,custom}.yaml` (per ADR-0007).
  - `backend/tests/unit/metrics/` — one test module per metric: small seeded inputs, expected values verified against the upstream library's reference implementation when applicable.
  - `backend/tests/integration/metrics/test_registry_and_dispatch.py` — exercises the full `MetricRegistry` plus engine routing of `kind` to the correct worker pool.
- **Dependencies (optional groups)**:
  - `metrics-lexical` (default): `sacrebleu>=2.4`, `rouge-score>=0.1.2`, `nltk>=3.9`, `rapidfuzz>=3.9`. Light footprint; fine to be on by default.
  - `metrics-embedding`: `sentence-transformers>=3`, `bert-score>=0.3.13`, `torch>=2.4`.
  - `metrics-rag`: brings in NLI implementations and any ranking helpers (`scipy>=1.13`, `numpy>=2`).
  - `metrics-learned`: only adds judge-adapter-specific extras; the actual judge model is selected via the adapter registry from ADR-0003.
- **Patterns to follow**:
  - Each metric module exposes one public class plus one `register_metric(...)` call at module bottom. Importing `aef.metrics` brings every shipped metric into the registry.
  - All upstream-library imports are deferred to first construction (`def __init__: from sacrebleu import ...`), so importing `aef.metrics` does not pull `transformers` etc.
  - All metric outputs route their primary scalar through `value` and any breakdown through `sub_values`. Never invent a sibling field.
  - All metrics call `with timed(f"metric.{self.spec.name}")` inside `compute` so per-sample latency is captured.
  - Metric-level config (e.g., ROUGE variants list, embedding model id) lives on the metric's `MetricSpec.config: TypedConfigSubModel` — *not* a `Dict[str, Any]`.
- **Patterns to avoid**:
  - Do NOT add metric-specific branches in the engine (per ADR-0005). Pool routing comes from `MetricSpec.kind` plus `requires_gpu` / `is_remote`, nothing else.
  - Do NOT use `Dict[str, Any]` for metric outputs, even for "extras". Add a typed field or a registered `SubScore`.
  - Do NOT mutate `MetricInputs` from inside a metric. Inputs are read-only.
  - Do NOT silently fail on missing inputs. Either declare `applicable_when` so the engine skips, or raise a typed `MetricInputError` with the metric name and missing field.
  - Do NOT load multi-hundred-MB embedding/judge models at import time. Lazy-load on first `compute` call.
- **Configuration**: see ADR-0007 for the `configs/metrics/` group. Default selection (`metrics=default`) ships a balanced subset: BLEU, ROUGE (1/2/L), chrF, exact-match, semantic similarity, BERTScore, latency, token counts. The full v1 suite is a one-token override (`metrics=full`).
- **Migration steps**: greenfield.

### Verification

- [ ] `aef.metrics.base.Metric` is a `Protocol` with `spec`, `compute`, `compute_batch`, `aggregate`, `close`.
- [ ] `MetricResult` has fields `metric_name`, `metric_version`, `sample_idx`, `status`, `value`, `sub_values: list[SubScore]`, `compute_latency_ms`, `exception_class`, `exception_message` — with no `Dict[str, Any]` anywhere.
- [ ] `aef.metrics.registry.MetricRegistry` exposes `register_metric`, `build_metric`, and entry-point discovery for `aef.metrics`.
- [ ] After `import aef.metrics`, the registry contains every metric in the v1 default suite (§4).
- [ ] Each metric module's heavy upstream library is NOT imported at the top of the file (verifiable via grep + an import test that asserts only stdlib + pydantic are pulled by the bare `import aef.metrics`).
- [ ] Running the v1 default suite over a 5-row mock dataset with `MockChatModel` produces a populated `EvaluationRunResult.metric_results` list with one `MetricResult` per (metric, sample) pair plus aggregate `MetricResult` rows.
- [ ] RAG metrics return `status="skipped"` when their `applicable_when` is sample-dependent and the sample lacks `context`. RAG metrics whose `applicable_when` is statically incompatible with the dataset are filtered before execution starts (`MissingMetricInputError`).
- [ ] `MetricResult` round-trips through `model_dump()` / `model_validate()` for every shipped metric.
- [ ] `MetricResult` round-trips through SQLAlchemy persistence (per ADR-0006) without information loss for both scalar and variadic metrics.
- [ ] Pyright strict (per ADR-0010) reports zero errors on `aef.metrics.*`.
- [ ] Engine code (per ADR-0005) contains zero `isinstance(metric, X)` branches.
- [ ] CLI override `metrics=lexical_only` selects only `aef.metrics.lexical.*` entries; `metrics=full` selects everything; `metrics=default` selects the balanced subset documented in §4.

## Alternatives Considered

- **`BaseMetric` ABC + inheritance**: rejected. Same reasoning as ADR-0003 — Protocols are lighter, integrate better with Pyright (per ADR-0010), and do not force inheritance for thin third-party wrappers.
- **One giant `Metric.compute(input, candidate, reference, context, gold_context, metadata) -> MetricResult` signature** (no `MetricInputs`): rejected. The signature would change every time a new optional input appears, breaking every implementation. `MetricInputs` is a Pydantic model precisely so adding fields is additive.
- **Free-form `Dict[str, float]` outputs**: rejected outright by the strict-typing rule.
- **Per-metric standalone CLIs** (each metric ships its own runner): rejected. Loses composability, scoring of LLM outputs in batch, and the unified `EvaluationRunResult` shape that the dashboard relies on.
- **Use a third-party metric framework (TorchMetrics, RAGAS, evaluate)**: considered. Each is a great library, but they do not all share an interface — adopting any one of them as the contract would couple us to that library's lifecycle. Wrapping them as concrete `Metric` implementations behind our Protocol is strictly cheaper.
- **Ship the full toxicity / PII / hallucination / calibration / diversity suite at v1**: rejected. Each one carries non-trivial dependencies and (for the safety/PII slice) genuine ethical and operational complexity that warrants its own ADR. The v1 cut focuses on metrics that are uncontroversial and well-validated.

## More Information

- High-level architecture: [`../high_level_architecture.md`](../high_level_architecture.md) §8 (entire), §11.1 (chart library decisions affect rendering of these results).
- External references:
  - [Papineni et al., "BLEU: a Method for Automatic Evaluation of Machine Translation"](https://aclanthology.org/P02-1040/) — BLEU.
  - [Post, "A Call for Clarity in Reporting BLEU Scores"](https://aclanthology.org/W18-6319/) — SacreBLEU motivation and reproducible BLEU reporting.
  - [Lin, "ROUGE: A Package for Automatic Evaluation of Summaries"](https://aclanthology.org/W04-1013/) — ROUGE family.
  - [Popović, "chrF: character n-gram F-score for automatic MT evaluation"](https://aclanthology.org/W15-3049/) — chrF.
  - [Banerjee and Lavie, "METEOR: An Automatic Metric for MT Evaluation with Improved Correlation with Human Judgments"](https://aclanthology.org/W05-0909/) — METEOR.
  - [Zhang et al., "BERTScore: Evaluating Text Generation with BERT"](https://arxiv.org/abs/1904.09675) — BERTScore.
  - [Reimers and Gurevych, "Sentence-BERT"](https://arxiv.org/abs/1908.10084) — sentence-transformer semantic similarity.
  - [RAGAS documentation](https://docs.ragas.io/) — common definitions for RAG faithfulness, answer relevancy, context precision, and context recall. This framework wraps the ideas behind a stricter typed contract rather than adopting RAGAS as the framework contract.
  - [Manning, Raghavan, and Schütze, "Introduction to Information Retrieval"](https://nlp.stanford.edu/IR-book/) — ranking metrics such as MRR, nDCG, and recall@k.
  - [RapidFuzz documentation](https://rapidfuzz.github.io/RapidFuzz/) — fuzzy string matching implementation reference.
  - [Python entry points specification](https://packaging.python.org/en/latest/specifications/entry-points/) — plugin discovery mechanism for third-party metrics.
- Related ADRs:
  - [`0003-adapter-architecture-for-models-and-datasets.md`](0003-adapter-architecture-for-models-and-datasets.md) — adapter capabilities and Pydantic specs are the prior art this ADR mirrors.
  - [`0005-execution-engine-local-and-distributed.md`](0005-execution-engine-local-and-distributed.md) — `MetricKind` plus `requires_gpu` / `is_remote` drive worker-pool routing.
  - [`0006-persistence-sqlite-default-postgres-swap-in.md`](0006-persistence-sqlite-default-postgres-swap-in.md) — `metric_results` table schema; `sub_values` is JSON-text only when fundamentally variadic.
  - [`0007-cli-configuration-with-hydra-and-hydra-zen.md`](0007-cli-configuration-with-hydra-and-hydra-zen.md) — `metrics` config group selects metric sets.
  - [`0011-testing-strategy-and-mock-adapters.md`](0011-testing-strategy-and-mock-adapters.md) — mock-driven metric tests against seeded inputs.
  - [`0012-logging-and-telemetry-contract.md`](0012-logging-and-telemetry-contract.md) — `compute_latency_ms` per metric flows into `TelemetryReport`.
  - [`0014-llm-as-judge-contract-and-bias-mitigation.md`](0014-llm-as-judge-contract-and-bias-mitigation.md) — LLM-as-judge contract specializes the `learned` family.
- Revisit triggers:
  - A metric needs a third structured output that does not fit `value` + `sub_values` (e.g., a confusion matrix). Consider a typed extension rather than `Dict[str, Any]`.
  - A user reports that a default metric's score is meaningfully different from the upstream library's reference. Pin the upstream library more tightly and re-verify.
  - The v1.x suggestions (toxicity, PII, hallucination-NLI, calibration, diversity) are ready to ship — write per-family ADRs and add to the registry.
