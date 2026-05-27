"""Metric Pydantic contracts: kinds, inputs, results, sub-scores, applicability.

Mirrors the adapter contract one-to-one (per ADR-0004 §1) so future
contributors learn one shape, not two: a typed Protocol consumes a typed
input model and returns a typed result model. ``Dict[str, Any]`` is
forbidden — variadic outputs use :class:`SubScore`.

# ADR: Default Metric Suite and Metric-Plugin Contract
# See: adr/0004-default-metric-suite-and-plugin-contract.md
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from backend.contracts.adapter_spec import CostReporting
from backend.contracts.primitives import GenerationResponse, RetrievedChunk, SampleMetadata


class MetricKind(StrEnum):
    """Top-level metric family used for engine pool routing per ADR-0005 §5."""

    LEXICAL = "lexical"
    EMBEDDING = "embedding"
    LEARNED = "learned"
    RAG = "rag"
    OPERATIONAL = "operational"


class MetricStatus(StrEnum):
    """Outcome of a single metric computation."""

    OK = "ok"
    ERROR = "error"
    SKIPPED = "skipped"


class SubScore(BaseModel):
    """One named sub-value emitted by a variadic metric.

    Examples: per-class precision, per-token confidence, and ROUGE-1/2/L
    variants. Anything richer than a scalar primary value goes here, never in
    ``Dict[str, Any]``.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * name: Stable sub-metric identifier (for example ``rouge-1``).
    * value: Numeric sub-score on the metric's scale.
    * notes: Optional human-readable annotation for dashboards or logs.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    value: float
    notes: str | None = None


class MetricApplicability(BaseModel):
    """Predicates the engine evaluates per-sample to decide skip vs run.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * requires_reference: Skip when the sample has no single ``reference`` string.
    * requires_references: Skip when the sample has no ``references`` list.
    * requires_context: Skip when the sample has no retrieved ``context`` chunks.
    * requires_gold_context: Skip when the sample has no ``gold_context`` chunks.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    requires_reference: bool = False
    requires_references: bool = False
    requires_context: bool = False
    requires_gold_context: bool = False


MetricRequiredInput = Literal[
    "reference",
    "references",
    "context",
    "gold_context",
]


class MetricSpec(BaseModel):
    """Identity, kind, and pool-routing knobs for a metric.

    Stored on every :class:`MetricResult` so persistence reproduces the
    full configuration the run used. The metric registry resolves a
    spec to a concrete metric implementation by ``name``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    kind: MetricKind
    version: str = Field(min_length=1, default="1.0")
    required_inputs: frozenset[MetricRequiredInput] = Field(
        default_factory=frozenset[MetricRequiredInput],
    )
    requires_gpu: bool = False
    is_remote: bool = False
    cost_reporting: CostReporting = "none"
    applicable_when: MetricApplicability = Field(
        default_factory=MetricApplicability,
    )
    config: dict[str, str] = Field(default_factory=dict[str, str])

    @field_serializer("required_inputs")
    def _serialize_required_inputs(
        self,
        value: frozenset[MetricRequiredInput],
    ) -> list[MetricRequiredInput]:
        """
        Serialize the field for JSON export.

        :param value: Value to inspect or transform.

        :return: A :class:`list[MetricRequiredInput]` instance.
        """
        return sorted(value)


class MetricInputs(BaseModel):
    """Per-sample inputs visible to a metric (per ADR-0004 §1).

    ``generation`` is optional and carries the full
    :class:`GenerationResponse` for operational metrics
    (latency / token counts / cost / output validity). Lexical and
    embedding metrics ignore it; the engine always populates it.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * sample_idx: Zero-based index of the sample within the run.
    * input: Original dataset prompt for this sample.
    * candidate: Model output being scored.
    * reference: Single gold answer when present on the sample.
    * references: Multiple gold answers when present on the sample.
    * context: Retrieved passages supplied at generation time.
    * gold_context: Gold passages for RAG metrics when present.
    * sample_metadata: Optional structured tags from the dataset.
    * generation: Full generation response; required for operational metrics.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    sample_idx: Annotated[int, Field(ge=0)]
    input: str
    candidate: str
    reference: str | None = None
    references: list[str] | None = None
    context: list[RetrievedChunk] | None = None
    gold_context: list[RetrievedChunk] | None = None
    sample_metadata: SampleMetadata | None = None
    generation: GenerationResponse | None = None


class MetricResult(BaseModel):
    """Typed, variadic-safe metric output (per ADR-0004 §2).

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * metric_name: Registry name of the metric that produced this result.
    * metric_version: Version string of the metric implementation.
    * sample_idx: Sample index when this is a per-sample result; ``None`` for aggregates.
    * status: Outcome of the computation (ok, error, or skipped).
    * value: Primary scalar score when the metric produced one.
    * sub_values: Named sub-scores when the metric is variadic.
    * compute_latency_ms: Wall-clock time spent computing this result.
    * exception_class: Exception type name when ``status`` is error.
    * exception_message: Exception message when ``status`` is error.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric_name: str = Field(min_length=1)
    metric_version: str = Field(min_length=1)
    sample_idx: Annotated[int | None, Field(ge=0)] = None
    status: MetricStatus
    value: float | None = None
    sub_values: list[SubScore] = Field(default_factory=list[SubScore])
    compute_latency_ms: Annotated[float, Field(ge=0.0)] = 0.0
    exception_class: str | None = None
    exception_message: str | None = None
