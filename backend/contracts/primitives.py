"""Leaf-level Pydantic shapes shared by every contract module.

This module lives at the bottom of the import graph: it has no sibling
dependencies inside :mod:`backend.contracts` and therefore breaks the
import-cycle that would otherwise form between
:mod:`backend.contracts.adapter_spec`, :mod:`backend.contracts.metric_result`,
:mod:`backend.contracts.run`, and :mod:`backend.contracts.telemetry`.

Public consumers should import from :mod:`backend.contracts` directly; this
module's split is an implementation detail of the strict-typing rule.

# ADR: Adapter Architecture for Models and Datasets
# See: adr/0003-adapter-architecture-for-models-and-datasets.md
# ADR: Execution Engine — Local and Distributed
# See: adr/0005-execution-engine-local-and-distributed.md
# ADR: LLM-as-Judge Contract and Bias-Mitigation Defaults
# See: adr/0014-llm-as-judge-contract-and-bias-mitigation.md
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Chat / generation primitives
# ---------------------------------------------------------------------------

ChatRole = Literal["system", "user", "assistant", "tool"]
"""Closed set of roles the chat-shaped adapters accept."""


class ChatMessage(BaseModel):
    """One message in a chat-shaped generation request.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * role: Speaker role in the chat transcript (system, user, assistant, or tool).
    * content: Text payload for this message.
    * name: Optional speaker label when the role is ``tool``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: ChatRole
    content: str
    name: str | None = None


class GenerationConfig(BaseModel):
    """Runtime-configurable generation parameters per ADR-0003 §4.

    Every field is optional; ``None`` means "use the adapter's default".
    Adapters MUST honor every field in
    :attr:`ModelCapabilities.supported_sampling_parameters` and MUST raise
    :class:`UnsupportedSamplingParameterError` when an unsupported field is set.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * temperature: Sampling temperature; higher values increase randomness.
    * top_k: Limit sampling to the top *k* logits by probability mass.
    * top_p: Nucleus sampling cutoff on cumulative token probability.
    * repetition_penalty: Multiplier penalizing repeated tokens (values above 1.0).
    * max_output_tokens: Hard cap on generated tokens for this call.
    * seed: RNG seed for reproducible decoding when the adapter supports it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    temperature: Annotated[float | None, Field(ge=0.0, le=2.0)] = None
    top_k: Annotated[int | None, Field(ge=1)] = None
    top_p: Annotated[float | None, Field(gt=0.0, le=1.0)] = None
    repetition_penalty: Annotated[float | None, Field(gt=0.0)] = None
    max_output_tokens: Annotated[int | None, Field(ge=1)] = None
    seed: Annotated[int | None, Field(ge=0)] = None


class Usage(BaseModel):
    """Token / cost accounting reported by an adapter for one call.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * prompt_tokens: Tokens consumed by the prompt side of the call.
    * completion_tokens: Tokens produced in the model output.
    * total_tokens: Combined prompt and completion token count when reported.
    * cost_usd: Estimated dollar cost for the call when the adapter can compute it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_tokens: Annotated[int | None, Field(ge=0)] = None
    completion_tokens: Annotated[int | None, Field(ge=0)] = None
    total_tokens: Annotated[int | None, Field(ge=0)] = None
    cost_usd: Annotated[float | None, Field(ge=0.0)] = None


class GenerationRequest(BaseModel):
    """Chat-shaped generation request handed to a :class:`ModelAdapter`.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * messages: Ordered chat history; must contain at least one message.
    * sampling: Generation parameters applied to this request.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    messages: list[ChatMessage] = Field(min_length=1)
    sampling: GenerationConfig = Field(default_factory=GenerationConfig)


class GenerationResponse(BaseModel):
    """Chat-shaped generation response returned by a :class:`ModelAdapter`.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * text: Decoded model output text.
    * finish_reason: Provider-specific stop reason (for example ``stop`` or ``length``).
    * usage: Token and cost accounting for this call.
    * latency_ms: Wall-clock latency measured by the adapter for this call.
    * trace: Optional diagnostic strings (tool calls, routing notes) for debugging.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    finish_reason: str | None = None
    usage: Usage = Field(default_factory=Usage)
    latency_ms: Annotated[float, Field(ge=0.0)] = 0.0
    trace: list[str] = Field(default_factory=list[str])


# ---------------------------------------------------------------------------
# Dataset / sample primitives
# ---------------------------------------------------------------------------


class RetrievedChunk(BaseModel):
    """A single retrieved chunk supplied alongside a sample (RAG).

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * text: Chunk body passed to the model or metric.
    * score: Retriever relevance score when the dataset provides one.
    * chunk_id: Stable identifier for this chunk within the corpus.
    * source: Provenance label (file, URL, document id) for the chunk.
    * relevance_label: Gold relevance flag for RAG metrics when available.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    score: float | None = None
    chunk_id: str | None = None
    source: str | None = None
    relevance_label: bool | None = None


class SampleMetadata(BaseModel):
    """Typed sample metadata — the explicit alternative to ``Dict[str, Any]``.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * dataset_split: Split name (train, validation, test) when the dataset tags it.
    * category: Coarse task or topic label for filtering and reporting.
    * difficulty: Ordinal difficulty bucket for stratified analysis.
    * language: BCP-47 or dataset-specific language code for the sample.
    * tags: Free-form labels attached by the dataset adapter.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_split: str | None = None
    category: str | None = None
    difficulty: Literal["easy", "medium", "hard"] | None = None
    language: str | None = None
    tags: list[str] = Field(default_factory=list[str])


class EvaluationSample(BaseModel):
    """One row produced by a :class:`DatasetAdapter`.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * idx: Zero-based row index within the dataset for this run.
    * input: Prompt or question text fed to the model under test.
    * reference: Single gold answer when the task has one reference string.
    * references: Multiple acceptable gold answers when the task allows variants.
    * context: Retrieved passages supplied to the model at generation time.
    * gold_context: Gold passages used by RAG metrics (may differ from ``context``).
    * metadata: Optional structured tags from the dataset adapter.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    idx: Annotated[int, Field(ge=0)]
    input: str
    reference: str | None = None
    references: list[str] | None = None
    context: list[RetrievedChunk] | None = None
    gold_context: list[RetrievedChunk] | None = None
    metadata: SampleMetadata | None = None


# ---------------------------------------------------------------------------
# Pipeline / engine primitives
# ---------------------------------------------------------------------------

PipelineStage = Literal[
    "setup",
    "generation",
    "scoring",
    "persist",
    "teardown",
]
"""Closed set of pipeline stages used by the engine and observability."""


EngineKind = Literal["local", "distributed"]
"""Top-level engine selector."""


EngineQueueName = Literal["generation", "scoring_cpu", "scoring_judge"]
"""Stable identifiers for the engine's three typed queues (per ADR-0005)."""


class EngineQueueConfig(BaseModel):
    """Sizing knobs for one of the engine's typed queues.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * pool_size: Number of concurrent workers draining this queue.
    * max_queue_depth: Maximum in-flight tasks before producers back-pressure.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pool_size: Annotated[int, Field(ge=0)] = 1
    max_queue_depth: Annotated[int, Field(ge=1)] = 16


def _default_engine_queues() -> dict[EngineQueueName, EngineQueueConfig]:
    """
    Return the default per-queue sizing for :class:`EngineConfig`.

    :return: :class:`EngineQueueName` instance.
    """
    return {
        "generation": EngineQueueConfig(pool_size=1, max_queue_depth=16),
        "scoring_cpu": EngineQueueConfig(pool_size=2, max_queue_depth=32),
        "scoring_judge": EngineQueueConfig(pool_size=0, max_queue_depth=16),
    }


class EngineConfig(BaseModel):
    """Single engine config consumed by :class:`ExecutionEngine.spec`.

    Per ADR-0005 §1 there is no separate ``EngineSpec``. The CLI builds this
    model via ``hydra-zen``; the API constructs it when a run is launched.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * kind: Selector between local in-process and distributed Celery execution.
    * micro_batch_size: Number of samples batched before a scoring flush.
    * micro_batch_timeout_ms: Max wait (ms) to fill a micro-batch before flushing.
    * broker_url: Redis (or compatible) URL for the distributed engine.
    * acks_late: When ``True``, Celery acknowledges tasks only after completion.
    * queues: Per-queue worker pool and depth limits (generation, scoring_cpu, scoring_judge).
    * cancel_grace_seconds: Seconds to wait for in-flight work after cancellation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: EngineKind = "local"
    micro_batch_size: Annotated[int, Field(ge=1)] = 1
    micro_batch_timeout_ms: Annotated[int, Field(ge=0)] = 25
    broker_url: str | None = None
    acks_late: bool = True
    queues: dict[EngineQueueName, EngineQueueConfig] = Field(
        default_factory=_default_engine_queues,
    )
    cancel_grace_seconds: Annotated[int, Field(ge=0)] = 30


class OutputConfig(BaseModel):
    """Where and what an evaluation run writes to disk.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * base_dir: Root directory under which run artifacts are created.
    * write_result_json: When ``True``, emit the full :class:`EvaluationRunResult` JSON.
    * write_metrics_csv: When ``True``, emit per-metric CSV summaries.
    * write_plots: When ``True``, emit visualization artifacts (deferred in skeleton).
    * write_run_log: When ``True``, emit a structured run log alongside results.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_dir: str = "outputs"
    write_result_json: bool = True
    write_metrics_csv: bool = True
    write_plots: bool = False
    write_run_log: bool = True


# ---------------------------------------------------------------------------
# Judge primitives (per ADR-0014)
# ---------------------------------------------------------------------------

RubricScale = Literal["binary", "likert_5", "likert_7", "score_0_10"]
"""Closed set of judge rating scales supported in v1."""


RubricAggregation = Literal["mean", "min", "weighted_mean", "none"]
"""How a rubric's per-criterion scores collapse to a single ``overall``."""


class RubricCriterion(BaseModel):
    """One named rating dimension inside a :class:`Rubric`.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * name: Short identifier for this criterion (stable across rubric versions).
    * description: Prompt text explaining what the judge should rate.
    * scale: Closed rating scale for this criterion.
    * higher_is_better: When ``True``, larger scores mean better quality.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    scale: RubricScale
    higher_is_better: bool = True


class Rubric(BaseModel):
    """A judge rubric — what the judge LLM scores against."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    criteria: list[RubricCriterion] = Field(min_length=1)
    aggregation: RubricAggregation = "mean"
    weights: list[float] | None = None

    @model_validator(mode="after")
    def _validate_weights(self) -> Rubric:
        """
        Validate model fields after construction.

        :return: A :class:`Rubric` instance.
        """
        if self.aggregation == "weighted_mean":
            if self.weights is None:
                raise ValueError("weighted_mean aggregation requires `weights`")
            if len(self.weights) != len(self.criteria):
                raise ValueError(
                    "len(weights) must equal len(criteria) for weighted_mean",
                )
        return self


class CriterionScore(BaseModel):
    """The judge's score on one rubric criterion.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * criterion: Name of the criterion being scored (matches :class:`RubricCriterion`).
    * score: Numeric rating on the criterion's scale.
    * rationale: Judge explanation supporting the score (required by ADR-0014).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    criterion: str = Field(min_length=1)
    score: float
    rationale: str = Field(min_length=1)


class RubricScore(BaseModel):
    """The judge's structured output for one judgment.

    ``overall`` is computed framework-side from ``criteria_scores`` per
    :attr:`Rubric.aggregation` (per ADR-0014 §2). The judge does NOT
    compute the aggregate.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * rubric_name: Name of the rubric that produced this score.
    * rubric_version: Version string of the rubric definition.
    * criteria_scores: Per-criterion scores returned by the judge.
    * overall: Framework-computed aggregate when aggregation is configured.
    * notes: Optional free-form judge commentary.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rubric_name: str
    rubric_version: str
    criteria_scores: list[CriterionScore]
    overall: float | None = None
    notes: str | None = None


class PairwisePreference(BaseModel):
    """Output of a pairwise judge comparing two candidates.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * winner: Which candidate won, or ``tie`` when indistinguishable.
    * confidence: Judge confidence in the preference on ``[0, 1]``.
    * score_a: Rubric scores for candidate A.
    * score_b: Rubric scores for candidate B.
    * swap_agreed: When ``True``, position-swap mitigation did not flip the winner.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    winner: Literal["A", "B", "tie"]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    score_a: RubricScore
    score_b: RubricScore
    swap_agreed: bool = True


class BiasMitigation(BaseModel):
    """Default bias-mitigation knobs for judge metrics (ADR-0014 §4).

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * position_swap: Run pairwise comparisons with candidates swapped and compare outcomes.
    * length_anchor: Normalize scores when candidate lengths differ materially.
    * style_anchor: Anchor scoring style across candidates in one batch.
    * self_preference_warning: Flag when the judge model may favor its own family.
    * deterministic: Pin decoding to temperature 0 and the run seed when supported.
    * require_rationale: Reject judge outputs that omit per-criterion rationales.
    * parser_retries: How many times to retry parsing malformed judge JSON.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    position_swap: bool = True
    length_anchor: bool = True
    style_anchor: bool = True
    self_preference_warning: bool = True
    deterministic: bool = True
    require_rationale: bool = True
    parser_retries: Annotated[int, Field(ge=0, le=10)] = 2


class JudgmentRequest(BaseModel):
    """Input passed to :meth:`JudgeAdapter.judge`.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * sample_idx: Index of the sample under judgment within the run.
    * sample_input: Original dataset prompt for context.
    * candidate: Primary model output being scored.
    * candidate_b: Second candidate for pairwise judging; ``None`` for single-candidate.
    * reference: Optional gold answer shown to the judge.
    * rubric: Rubric definition the judge must apply.
    * rendered_prompt: Fully rendered judge prompt sent to the adapter.
    * bias_mitigation: Bias-mitigation knobs applied to this judgment.
    * sampling: Decoding parameters for the judge model call.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    sample_idx: Annotated[int, Field(ge=0)]
    sample_input: str
    candidate: str
    candidate_b: str | None = None
    reference: str | None = None
    rubric: Rubric
    rendered_prompt: str
    bias_mitigation: BiasMitigation = Field(default_factory=BiasMitigation)
    sampling: GenerationConfig = Field(default_factory=GenerationConfig)


class JudgmentResponse(BaseModel):
    """Output of :meth:`JudgeAdapter.judge`.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * score: Structured rubric scores for the judgment.
    * pairwise: Pairwise preference details when ``candidate_b`` was provided.
    * usage: Token and cost accounting for the judge call.
    * latency_ms: Wall-clock latency of the judge call.
    * deterministic_best_effort: Whether deterministic decoding was honored.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    score: RubricScore
    pairwise: PairwisePreference | None = None
    usage: Usage = Field(default_factory=Usage)
    latency_ms: Annotated[float, Field(ge=0.0)] = 0.0
    deterministic_best_effort: bool = False
