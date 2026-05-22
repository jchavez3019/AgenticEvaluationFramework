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
    """One message in a chat-shaped generation request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: ChatRole
    content: str
    name: str | None = None


class GenerationConfig(BaseModel):
    """Runtime-configurable generation parameters per ADR-0003 §4.

    Every field is optional; ``None`` means "use the adapter's default".
    Adapters MUST honor every field appearing in their
    :attr:`ModelCapabilities.supported_sampling_parameters` set and MUST
    raise :class:`UnsupportedSamplingParameterError` when an explicitly
    set field is not in that set.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    temperature: Annotated[float | None, Field(ge=0.0, le=2.0)] = None
    top_k: Annotated[int | None, Field(ge=1)] = None
    top_p: Annotated[float | None, Field(gt=0.0, le=1.0)] = None
    repetition_penalty: Annotated[float | None, Field(gt=0.0)] = None
    max_output_tokens: Annotated[int | None, Field(ge=1)] = None
    seed: Annotated[int | None, Field(ge=0)] = None


class Usage(BaseModel):
    """Token / cost accounting reported by an adapter for one call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_tokens: Annotated[int | None, Field(ge=0)] = None
    completion_tokens: Annotated[int | None, Field(ge=0)] = None
    total_tokens: Annotated[int | None, Field(ge=0)] = None
    cost_usd: Annotated[float | None, Field(ge=0.0)] = None


class GenerationRequest(BaseModel):
    """Chat-shaped generation request handed to a :class:`ModelAdapter`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    messages: list[ChatMessage] = Field(min_length=1)
    sampling: GenerationConfig = Field(default_factory=GenerationConfig)


class GenerationResponse(BaseModel):
    """Chat-shaped generation response returned by a :class:`ModelAdapter`."""

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
    """A single retrieved chunk supplied alongside a sample (RAG)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    score: float | None = None
    chunk_id: str | None = None
    source: str | None = None
    relevance_label: bool | None = None


class SampleMetadata(BaseModel):
    """Typed sample metadata — the explicit alternative to ``Dict[str, Any]``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dataset_split: str | None = None
    category: str | None = None
    difficulty: Literal["easy", "medium", "hard"] | None = None
    language: str | None = None
    tags: list[str] = Field(default_factory=list[str])


class EvaluationSample(BaseModel):
    """One row produced by a :class:`DatasetAdapter`."""

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
    """Sizing knobs for one of the engine's typed queues."""

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

    Per the ADR-0005 §1 clarification, the engine has exactly one
    Pydantic model — there is no separate ``EngineSpec``. The CLI builds
    this model via ``hydra-zen`` (per ADR-0007); the API constructs it
    directly when a frontend launches a run.
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
    """Where and what an evaluation run writes to disk."""

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
    """One named rating dimension inside a :class:`Rubric`."""

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
    """The judge's score on one rubric criterion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    criterion: str = Field(min_length=1)
    score: float
    rationale: str = Field(min_length=1)


class RubricScore(BaseModel):
    """The judge's structured output for one judgment.

    ``overall`` is computed framework-side from ``criteria_scores`` per
    :attr:`Rubric.aggregation` (per ADR-0014 §2). The judge does NOT
    compute the aggregate.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rubric_name: str
    rubric_version: str
    criteria_scores: list[CriterionScore]
    overall: float | None = None
    notes: str | None = None


class PairwisePreference(BaseModel):
    """Output of a pairwise judge comparing two candidates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    winner: Literal["A", "B", "tie"]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    score_a: RubricScore
    score_b: RubricScore
    swap_agreed: bool = True


class BiasMitigation(BaseModel):
    """Default bias-mitigation knobs for judge metrics (ADR-0014 §4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    position_swap: bool = True
    length_anchor: bool = True
    style_anchor: bool = True
    self_preference_warning: bool = True
    deterministic: bool = True
    require_rationale: bool = True
    parser_retries: Annotated[int, Field(ge=0, le=10)] = 2


class JudgmentRequest(BaseModel):
    """Input passed to :meth:`JudgeAdapter.judge`."""

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
    """Output of :meth:`JudgeAdapter.judge`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    score: RubricScore
    pairwise: PairwisePreference | None = None
    usage: Usage = Field(default_factory=Usage)
    latency_ms: Annotated[float, Field(ge=0.0)] = 0.0
    deterministic_best_effort: bool = False
