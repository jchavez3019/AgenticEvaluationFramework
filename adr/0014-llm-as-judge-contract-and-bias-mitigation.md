---
status: proposed
date: 2026-05-18
decision-makers: jorgejc2
---

# LLM-as-Judge Contract and Bias-Mitigation Defaults

## Context and Problem Statement

LLM-as-judge metrics evaluate a candidate's quality by asking another LLM ("the judge") to rate it against a rubric. In open-ended generation, where lexical and embedding metrics correlate poorly with human judgment, judges have become the de-facto bridge to human-aligned evaluation. They are also where the single biggest reproducibility, fairness, and contract-design risks in this framework live:

- **Position bias** — pairwise judges over-prefer the first candidate.
- **Length / verbosity bias** — judges reward longer answers regardless of quality.
- **Self-preference / "narcissism" bias** — judges from the same model family score outputs from that family higher.
- **Stylistic bias** — judges prefer fluent / confident outputs over correct-but-hedged ones.
- **Prompt drift** — small wording changes in the rubric prompt produce large score shifts.
- **Output schema fragility** — judges hallucinate fields, return unparseable JSON, or invent rubric dimensions.

The high-level architecture document (§8) commits to LLM-as-judge as part of the default metric suite. ADR-0003 declares `JudgeAdapter` as a specialization of `ModelAdapter`. ADR-0004 places the `learned` family (`llm_judge`, `pairwise_judge`, `g_eval`) inside the metric registry. None of those ADRs answer the harder question: _what does a judge actually receive, what does it return, and what defaults make its scores reproducible and as bias-free as we can make them in v1?_

This ADR specifies the judge contract and the bias-mitigation defaults that the in-tree judge metrics enforce.

## Decision Drivers

- **Reproducibility.** Two runs with the same `EvaluationRunRequest`, same judge adapter, same `seed`, and the same candidates must produce byte-identical `MetricResult` rows.
- **Schema reliability.** Judge output must always be a typed, validated Pydantic object. JSON parse failures are a recoverable, recorded error, not a silent zero-score.
- **Bias control by default.** Position-swap for pairwise, length normalization signals on rubric, and explicit "do not reward verbosity" anchoring in prompts — all on by default. Users opt _out_, not in.
- **Adapter-agnostic.** A judge can be a local HF model, an Ollama model, or a cloud API. The contract must be identical regardless.
- **Cost and latency awareness.** Judges are themselves generation workloads; the operational metrics (`cost`, `token_counts`, `latency`) capture per-judgment overhead.
- **Explainability.** Every judgment carries a free-text `rationale` so the dashboard can show _why_ the judge scored a sample as it did.

## Decision

Adopt a single typed `JudgeAdapter` Protocol, a `RubricScore` Pydantic model that every judge metric returns inside a `MetricResult.sub_values`, three concrete in-tree judge metrics (`llm_judge`, `pairwise_judge`, `g_eval`), and a fixed set of bias-mitigation defaults that those metrics apply unless explicitly disabled.

### 1. `JudgeAdapter` Protocol

`JudgeAdapter` extends the generic `ModelAdapter` from ADR-0003 with a structured-output contract:

```python
class JudgeAdapterSpec(ModelAdapterSpec):
    judge_kind: Literal["single", "pairwise", "g_eval"]
    rubric: Rubric  # see §2 below
    response_schema: type[RubricScore]  # the Pydantic class the judge must return
    deterministic: bool = True  # default ON: temperature=0, seed fixed


class JudgeAdapter(ModelAdapter, Protocol):
    spec: JudgeAdapterSpec

    async def judge(
        self, request: JudgmentRequest
    ) -> JudgmentResponse: ...
```

`judge()` is a wrapper around `generate()` that:

1. Renders the rubric + candidates into a prompt using the adapter's prompt template.
2. Invokes the underlying LLM with `temperature=0` and a fixed `seed` (when `deterministic=True`, the default).
3. Parses the LLM's text output into `RubricScore` via Pydantic. Parse failure is wrapped as `JudgeOutputParseError` and surfaces as `MetricResult(status="error", exception_class="JudgeOutputParseError", ...)` — the run continues, the offending sample is recorded.
4. Records token counts and cost on `JudgmentResponse.usage` (mirrors `GenerationResponse`).

Adapters that wrap chat-completions APIs use the API's structured-output / JSON-schema mode when available; on cloud providers that do not support JSON-schema enforcement, the adapter retries up to N times (configurable, default 2) with the parser error fed back into the prompt before giving up. This is a per-judge setting, not framework-wide.

### 2. `Rubric` and `RubricScore`

```python
class RubricCriterion(BaseModel):
    name: str                    # e.g., "factual_accuracy"
    description: str             # one-sentence definition the judge sees
    scale: Literal["binary", "likert_5", "likert_7", "score_0_10"]
    higher_is_better: bool = True


class Rubric(BaseModel):
    name: str
    version: str
    criteria: list[RubricCriterion]
    aggregation: Literal["mean", "min", "weighted_mean", "none"] = "mean"
    weights: list[float] | None = None  # required iff aggregation == "weighted_mean"


class CriterionScore(BaseModel):
    criterion: str               # matches RubricCriterion.name
    score: float                 # raw score on the criterion's scale
    rationale: str               # 1–3 sentences explaining the score


class RubricScore(BaseModel):
    rubric_name: str
    rubric_version: str
    criteria_scores: list[CriterionScore]
    overall: float | None        # populated by aggregation; None if aggregation == "none"
    notes: str | None            # judge-level free-form explanation
```

The judge LLM is _required_ to return a JSON object that round-trips through `RubricScore`. The prompt template explicitly shows the schema to the judge (one-shot example included). Adapters that support API-level JSON-schema enforcement use it; the rest rely on parser+retry.

`RubricScore.overall` is computed deterministically from `criteria_scores` according to `Rubric.aggregation`. The judge does _not_ compute the overall — that is framework-side, so changing aggregation does not require re-running the judge.

`MetricResult.value` for a judge metric is `RubricScore.overall` (or `None` when aggregation is `"none"` and the user wants the criterion breakdown only). `MetricResult.sub_values` carries one `SubScore` per `CriterionScore.criterion`, with `notes` set to the criterion's rationale truncated to a configurable length.

### 3. Three concrete judge metrics

#### `llm_judge` — single-answer rubric scoring

- Inputs: `candidate`, optionally `reference`, optionally `input` (the original prompt). The rubric specifies whether `reference` is required.
- Output: one `RubricScore` per sample.
- Default rubric (when the user does not supply one): a 5-criterion v1 rubric — `factual_accuracy`, `relevance`, `coherence`, `helpfulness`, `safety` — all on the `likert_5` scale, `higher_is_better=True`, mean aggregation.

#### `pairwise_judge` — A/B preference

- Inputs: `candidate_a`, `candidate_b`, common `input`, optionally `reference`. The metric is run when comparing two models on the same dataset (ADR-0005's multirun pattern provides the shape).
- Output: a `PairwisePreference` Pydantic model with `winner: Literal["A", "B", "tie"]`, `confidence: float`, plus the per-criterion `RubricScore` for each side.
- **Position-swap is on by default.** Each pairwise judgment is run twice — once with the candidate ordering as supplied, once swapped. Both judgments must agree for the result to count as `winner != "tie"`; disagreement collapses to `winner="tie"`. This single change cuts
  position-bias-driven false preferences by a substantial margin in published evaluations and
  costs only an extra judge call per pair. The main prior art is MT-Bench / Chatbot Arena and follow-up papers studying order, verbosity, and self-preference biases. Users may disable position-swap (`bias_mitigation.position_swap=false`) at the cost of recorded position bias on their results.

#### `g_eval` — multi-step / chain-of-thought structured judging

- Inputs: same as `llm_judge`.
- Procedure: the judge prompt follows the G-Eval pattern: explicitly list the evaluation criteria, ask the judge to derive intermediate evaluation steps, then emit a structured score for each criterion. The reasoning is captured in `RubricScore.notes` for inspection but is _not_ used to override the structured criterion scores.
- Difference from `llm_judge`: `llm_judge` is direct rubric scoring ("score this answer against these criteria"), while `g_eval` is a prompt-and-procedure template for decomposed evaluation. `g_eval` can still run on a model that was not trained with a special "CoT mode"; the distinction is in the metric's prompting protocol, not a model capability toggle. It also standardizes the intermediate-step prompt shape so two G-Eval runs are comparable across judge adapters.
- Suited to nuanced rubrics where simple direct scoring drifts (math reasoning, multi-step factuality, instruction following). It is more expensive in tokens than `llm_judge`, so it is not the default judge metric.

All three metrics share the same `JudgeAdapter`, the same prompt template family (versioned), and the same parsing/retry path. They differ only in how they call into it.

### 4. Default bias-mitigation settings

A typed `BiasMitigation` sub-model on each judge metric's spec:

```python
class BiasMitigation(BaseModel):
    position_swap: bool = True            # pairwise only; on by default
    length_anchor: bool = True            # add explicit "do not reward verbosity" instruction
    style_anchor: bool = True             # add explicit "ignore stylistic differences" instruction
    self_preference_warning: bool = True  # add explicit "do not favor your own family" when family is detected
    deterministic: bool = True            # temperature=0, fixed seed; reproducibility guarantee
    require_rationale: bool = True        # criterion scores without rationale are rejected
    parser_retries: int = 2               # JSON parse retry budget
```

All defaults are `on`. They are not optional behaviors hidden behind a feature flag — they are the framework's stance on what "default LLM-as-judge" means here. A user who wants raw, un-anchored judgments must explicitly set the relevant fields to `False` in their config; the dashboard surfaces this on every run-history row so a user comparing runs can immediately see whether bias mitigations were on.

`self_preference_warning` works by inspecting the family of both the candidate generator's adapter and the judge's adapter (`ModelAdapterSpec.family: Literal["openai", "anthropic", "gemini", "local-hf", "local-ollama", ...]`). If they match, a one-paragraph anchor is appended to the rubric prompt: _"You and the candidate share a model family. Evaluate strictly against the rubric and do not favor outputs from your family."_ This is a known imperfect mitigation; the dashboard warns the user and recommends using a judge from a different family when possible.

### 5. Prompt template versioning

Judge prompts are not freeform strings scattered through the codebase. They live under `aef.metrics.learned.prompts/` as versioned Jinja-2 templates:

```
prompts/
  v1/
    llm_judge.j2
    pairwise_judge.j2
    g_eval.j2
    anchors/
      length.j2
      style.j2
      self_preference.j2
```

- The active prompt version is captured on `MetricResult.metric_version` so a future change to the template does not retroactively alter old runs.
- A `prompts/v2/...` would constitute a new `metric_version` and is a new ADR if the change is non-trivial (e.g., changes the rubric schema visible to the model). Editing wording inside `v1/` is not allowed once `v1` ships; corrections go to `v2/`.

Jinja-2 is used because the prompt is a **template**, not a static text blob. The framework must insert a rubric, the user input, one or two candidate answers, optional references, optional bias-mitigation anchors, and the required JSON schema while keeping whitespace and escaping deterministic. Jinja-2 gives conditionals (`{% if reference %}`), loops (`{% for criterion in rubric.criteria %}`), whitespace controls, template inheritance / includes for anchors, and testable rendered-output snapshots.

### 6. Determinism and seeding

- `JudgeAdapterSpec.deterministic=True` (the default) sets `GenerationConfig.temperature=0`, fixes `GenerationConfig.seed` to the run's `seed` field, and pins the prompt-template version.
- For local HF judges, this combination plus `transformers`'s `set_seed(...)` produces deterministic outputs.
- For cloud APIs without honored seeds, "deterministic" is best-effort; the spec records `deterministic_best_effort=True` on the resulting `MetricResult` so the dashboard can flag runs whose reproducibility is not guaranteed by the provider.

### 7. Cost and pool routing

- Judge metrics declare `kind=LEARNED` (per ADR-0004) and inherit the routing rules from ADR-0005:
  - `is_remote=True` → `cloud_judge_api` pool. Rate-limit-bounded.
  - `is_remote=False`, `requires_gpu=True` → `local_gpu` _judge_ pool, distinct from the main generation pool.
- Every `RubricScore` carries the underlying judge call's `usage` (token counts, cost) so the dashboard can show "this run cost $X in judge fees, of which $Y was pairwise position-swap overhead".
- A run that uses pairwise judging with `position_swap=True` incurs roughly 2× the judge cost. The CLI's `validate_config` step (per ADR-0007) emits an estimated upper-bound cost when the user configures cloud judges, so there are no surprise bills.

### Non-goals

- We are NOT shipping a fine-tuned judge model in v1. The default judge is a configurable third-party model (cloud or local) chosen by the user.
- We are NOT building a "judge of judges" / meta-evaluation in v1.
- We are NOT supporting Likert scales beyond 5 / 7 or arbitrary custom scales in v1. Two scales are the canonical defaults.
- We are NOT calibrating judge scores to human preferences in v1. A future ADR can add a calibration metric; this ADR specifies the contract that calibration would consume.
- We are NOT supporting multi-turn judge conversations. Each judgment is one prompt → one structured response.

## Consequences

- Good, because judges are a real specialization of `ModelAdapter` rather than a parallel hierarchy. Users who add a custom judge follow exactly the path they would for a custom model adapter (per ADR-0003).
- Good, because `RubricScore` plus `SubScore` per criterion gives the dashboard a uniform render shape: every judge run has the same kind of output table, regardless of rubric.
- Good, because position-swap, length-anchor, style-anchor, and self-preference-warning are all _defaults_ — users who do nothing get the safer behavior. The dashboard always shows whether they were on.
- Good, because parser+retry plus `JudgeOutputParseError` gives schema-reliable judging without aborting the run on a single bad JSON output.
- Good, because prompt versioning means `metric_version` on `MetricResult` is meaningful: a v1 score from January and a v1 score from December are produced by the same prompt.
- Bad, because position-swap doubles pairwise cost. We accept this — pairwise judging is the most position-bias-prone shape and the cost is the price of trustable comparisons.
- Bad, because judges are still imperfect — `self_preference_warning` is a partial mitigation, not a fix. The dashboard's documentation of it must be honest about that.
- Bad, because deterministic seeding on cloud APIs is best-effort. We label such runs explicitly so reproducibility claims are not overstated.
- Neutral, because the `BiasMitigation` defaults are stronger than what some published harnesses ship. We accept being "more cautious by default" as the framework's point of view.

## Implementation Plan

- **Affected paths**:
  - `backend/src/aef/contracts/run.py` — adds `JudgmentRequest`, `JudgmentResponse`, `Rubric`, `RubricCriterion`, `CriterionScore`, `RubricScore`, `PairwisePreference`, `BiasMitigation` Pydantic models.
  - `backend/src/aef/contracts/adapter_spec.py` — adds `JudgeAdapterSpec` extending `ModelAdapterSpec` with `judge_kind`, `rubric`, `response_schema`, `deterministic`, `family`.
  - `backend/src/aef/adapters/models/base.py` — adds `JudgeAdapter` Protocol next to `ModelAdapter`.
  - `backend/src/aef/adapters/models/openai.py`, `anthropic.py`, `huggingface.py`, `ollama.py`, `langgraph.py` — each gains a corresponding `*JudgeAdapter` class that wraps the existing chat adapter with structured-output support and the parser+retry path.
  - `backend/src/aef/adapters/models/mocks.py` — `MockJudge` (already declared in ADR-0011) implements `JudgeAdapter` and consumes `MockJudgeScript` per ADR-0011.
  - `backend/src/aef/metrics/learned/llm_judge.py`, `pairwise_judge.py`, `g_eval.py` — three concrete metrics, each using a `JudgeAdapter` and applying the `BiasMitigation` defaults.
  - `backend/src/aef/metrics/learned/prompts/v1/` — Jinja-2 templates as in §5.
  - `backend/src/aef/metrics/learned/rubrics/default_v1.json` — the 5-criterion default rubric described in §3 (`llm_judge`).
  - `backend/tests/unit/metrics/learned/` — tests using `MockJudge` to verify position-swap collapses disagreements to `tie`, parser retries trigger on bad JSON, deterministic re-runs produce byte-identical results, and family-mismatch warnings fire correctly.
- **Dependencies**:
  - `metrics-learned` optional group: `jinja2>=3.1` for prompt templates. Jinja-2 is deliberately limited to prompt rendering; it is not used for arbitrary code execution and templates are shipped with the framework, not user-uploaded at runtime.
  - No new heavy dependencies; the actual model is selected through the existing adapter registry.
- **Patterns to follow**:
  - Every judge metric reads its `BiasMitigation` from the metric spec and applies it deterministically. The defaults in §4 are baked into `BiasMitigation`'s field defaults.
  - Every judge metric instantiates its `JudgeAdapter` via the registry from ADR-0003. No special-case construction inside the metric.
  - Every prompt template renders via `Jinja2Environment(autoescape=False)` with `keep_trailing_newline=False`. The rendered prompt is captured on `JudgmentRequest.prompt` for inclusion in `MetricResult.notes` (truncated; full prompt is recoverable via the rubric + template version).
  - Every judge call is wrapped in `with timed("metric.<name>")` (per ADR-0012). Token counts and cost on `JudgmentResponse.usage` flow into the operational metrics for the run.
  - `MetricResult.metric_version` includes both the metric semver and the prompt-template version: e.g., `"llm_judge:1.0+prompt:v1"`.
- **Patterns to avoid**:
  - Do NOT silently fall back to a zero-score on parser failure. Record `MetricResult(status="error", exception_class="JudgeOutputParseError", ...)`.
  - Do NOT let the judge compute the `overall` aggregation — the framework computes it from `criteria_scores` per the `Rubric.aggregation`.
  - Do NOT enable `position_swap=False` as a default. Override is allowed; default is not.
  - Do NOT inline judge prompts as Python f-strings. Templates live under `prompts/`.
  - Do NOT change a v1 prompt template after release. Add `v2/` and bump `metric_version`.
  - Do NOT use a judge with `temperature` > 0 by default. Determinism is the default; non-deterministic judging is opt-in and labeled.
- **Configuration**:
  - `metrics.<name>.judge_adapter` — selects the registered judge adapter (e.g., `openai-judge`, `mock-judge`).
  - `metrics.<name>.rubric` — either an inline `Rubric` or a string referencing a packaged rubric (e.g., `"default_v1"`).
  - `metrics.<name>.bias_mitigation.*` — overrides for the defaults in §4.
  - `metrics.<name>.parser_retries` — overrides the per-judge retry budget.
- **Migration steps**: greenfield.

### Verification

- [ ] `aef.contracts.run.RubricScore`, `PairwisePreference`, and `BiasMitigation` exist with the field shapes from §2 and §4.
- [ ] `JudgeAdapter` is a `Protocol` extending `ModelAdapter` with a `judge` method; pyright strict accepts every shipped concrete judge adapter.
- [ ] `MockJudge` implements `JudgeAdapter` and produces deterministic results from a `MockJudgeScript` per ADR-0011.
- [ ] Running `pairwise_judge` against `MockJudge` with two scripted judgments that disagree on a swapped pair produces `winner="tie"` (not the position-1 candidate).
- [ ] Running `llm_judge` twice with the same `seed`, same `MockJudge` script, and same candidates produces byte-identical `MetricResult` outputs.
- [ ] A judge that returns invalid JSON for one sample produces a `MetricResult` with `status="error"` and `exception_class="JudgeOutputParseError"` for that sample, and the run continues.
- [ ] `metric_version` on every judge `MetricResult` includes both metric semver and prompt-template version (e.g., `"llm_judge:1.0+prompt:v1"`).
- [ ] When the candidate-generator adapter and the judge adapter share a `family`, the rendered prompt contains the self-preference anchor (verifiable via a snapshot test on the rendered prompt).
- [ ] `Rubric.aggregation == "weighted_mean"` requires `weights` of equal length to `criteria`; otherwise `Rubric.model_validate(...)` raises.
- [ ] Disabling `position_swap` flips the rendered prompt's metadata flag and is reflected in `MetricResult.notes` and on the dashboard's run-history row.
- [ ] No file under `aef.metrics.learned.*` contains a literal judge prompt as a Python f-string (verifiable via `rg`).

## Alternatives Considered

- **No bias mitigations by default** (raw rubric scoring, user opts in). Rejected. The published evidence on position bias and length bias is overwhelming; shipping defaults that are known-bad is exactly the failure mode this ADR exists to prevent.
- **Free-form judge output (no `RubricScore` Pydantic schema)**. Rejected outright by the strict-typing rule and by the dashboard's need for uniform render shapes.
- **Embed prompts as Python f-strings inside metric modules.** Rejected. Prompt versioning becomes invisible, snapshot tests are clumsy, and contributors edit prompts ad-hoc.
- **Use a single `confidence` score instead of full `RubricScore`.** Rejected. Single-number judging is exactly what the rubric is designed to escape — it conflates dimensions and prevents per-criterion analysis.
- **Run all three judge metrics on every sample by default.** Rejected. Cost and latency would make even small datasets expensive. Users opt in per metric via the `metrics` config group.
- **Treat self-preference as solvable in v1.** Rejected. The mitigation is a warning anchor plus dashboard surfacing; we do not claim to fix it. Calibration / cross-family double-judging are future work.

## More Information

- High-level architecture: [`../high_level_architecture.md`](../high_level_architecture.md) §8 (LLM-as-judge family).
- External references:
  - [Jinja documentation](https://jinja.palletsprojects.com/) — template syntax and rendering semantics used for prompt templates.
  - [Liu et al., "G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment"](https://arxiv.org/abs/2303.16634) — source methodology for the `g_eval` metric family.
  - [Zheng et al., "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena"](https://arxiv.org/abs/2306.05685) — benchmark evidence and discussion of LLM judge agreement, limitations, and bias.
  - [Wang et al., "Large Language Models are not Fair Evaluators"](https://arxiv.org/abs/2305.17926) — analysis of position bias and other evaluator biases in pairwise judging.
  - [AlpacaEval documentation](https://tatsu-lab.github.io/alpaca_eval/) — representative judge-style instruction-following evaluation prior art and implementation reference.
- Related ADRs:
  - [`0003-adapter-architecture-for-models-and-datasets.md`](0003-adapter-architecture-for-models-and-datasets.md) — `JudgeAdapter` extends `ModelAdapter`. Capabilities (`is_remote`, `requires_gpu`, `family`) drive routing.
  - [`0004-default-metric-suite-and-plugin-contract.md`](0004-default-metric-suite-and-plugin-contract.md) — the `learned` family slot this ADR fills.
  - [`0005-execution-engine-local-and-distributed.md`](0005-execution-engine-local-and-distributed.md) — judge worker pool routing (`cloud_judge_api`, `local_gpu` judge pool).
  - [`0006-persistence-sqlite-default-postgres-swap-in.md`](0006-persistence-sqlite-default-postgres-swap-in.md) — `RubricScore` round-trips through `metric_results.sub_values_json`.
  - [`0010-code-quality-standards.md`](0010-code-quality-standards.md) — `f-string-judges` are forbidden; pyright strict catches missing `await`s in async judge calls.
  - [`0011-testing-strategy-and-mock-adapters.md`](0011-testing-strategy-and-mock-adapters.md) — `MockJudge` is how every judge metric test is written.
  - [`0012-logging-and-telemetry-contract.md`](0012-logging-and-telemetry-contract.md) — judge calls are timed and counted into the run's `TelemetryReport`.
- Revisit triggers:
  - Calibration to human preferences becomes a v1.x ask — open a calibration ADR that consumes `RubricScore`.
  - A new prompt version (v2) is needed — open a focused ADR documenting the schema or wording delta and the migration story.
  - Self-preference research yields a reliable mitigation beyond the warning anchor — promote it from "best-effort" to a real default and update this ADR.
  - A user operationally needs custom Likert scales beyond 5/7 — extend `RubricCriterion.scale` with a typed enum case rather than a free-form string.
