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

from aef.contracts.adapter_spec import CostReporting
from aef.contracts.primitives import GenerationResponse, RetrievedChunk, SampleMetadata


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

    Examples: per-class precision in a classification metric, per-token
    confidence, ROUGE-1/2/L variants. Anything richer than a scalar
    primary value goes here, never in ``Dict[str, Any]``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    value: float
    notes: str | None = None


class MetricApplicability(BaseModel):
    """Predicates the engine evaluates per-sample to decide skip vs run."""

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
        return sorted(value)


class MetricInputs(BaseModel):
    """Per-sample inputs visible to a metric (per ADR-0004 §1).

    ``generation`` is optional and carries the full
    :class:`GenerationResponse` for operational metrics
    (latency / token counts / cost / output validity). Lexical and
    embedding metrics ignore it; the engine always populates it.
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
    """Typed, variadic-safe metric output (per ADR-0004 §2)."""

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
