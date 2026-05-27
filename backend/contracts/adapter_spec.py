"""Adapter specs and capabilities — the typed identity of every adapter.

Every adapter family in the framework (model, dataset, judge, storage)
declares its identity, configuration, and runtime capabilities through a
Pydantic model defined here. The engine, metrics, persistence, and CLI
all consume these specs; no module reaches into adapter internals.

This module depends only on :mod:`backend.contracts.primitives` so the
contracts package has an acyclic import graph.

# ADR: Adapter Architecture for Models and Datasets
# See: adr/0003-adapter-architecture-for-models-and-datasets.md
# ADR: LLM-as-Judge Contract and Bias-Mitigation Defaults
# See: adr/0014-llm-as-judge-contract-and-bias-mitigation.md
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from backend.contracts.primitives import Rubric

SamplingParameter = Literal[
    "temperature",
    "top_k",
    "top_p",
    "repetition_penalty",
    "max_output_tokens",
    "seed",
]
"""Closed enumeration of generation parameters the framework exposes.

Adapters advertise which subset they honor via
``ModelCapabilities.supported_sampling_parameters``. Every adapter MUST
raise :class:`UnsupportedSamplingParameterError` if a request explicitly
sets a parameter not in its supported set (per ADR-0003 §4)."""


ModelFamily = Literal[
    "openai",
    "anthropic",
    "gemini",
    "local-hf",
    "local-ollama",
    "langgraph",
    "mock",
    "other",
]
"""High-level family used for self-preference detection (per ADR-0014 §4)."""


CostReporting = Literal["full", "tokens-only", "none"]
"""How an adapter reports cost.

``full`` includes per-call USD totals; ``tokens-only`` reports
prompt/completion token counts; ``none`` means the adapter cannot
compute either (typical for offline / mock adapters)."""


DatasetField = Literal["reference", "references", "context", "gold_context"]
"""Closed set of optional sample fields a dataset adapter may populate."""


class ModelCapabilities(BaseModel):
    """Static, declarative capabilities for a model adapter."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    supports_streaming: bool = False
    supports_tool_use: bool = False
    max_context_tokens: int | None = Field(default=None, ge=1)
    requires_gpu: bool = False
    is_remote: bool = False
    cost_reporting: CostReporting = "none"
    supported_sampling_parameters: frozenset[SamplingParameter] = Field(
        default_factory=frozenset[SamplingParameter],
    )
    family: ModelFamily = "other"

    @field_serializer("supported_sampling_parameters")
    def _serialize_supported_sampling_parameters(
        self,
        value: frozenset[SamplingParameter],
    ) -> list[SamplingParameter]:
        """
        Serialize the field for JSON export.

        :param value: Value to inspect or transform.

        :return: A :class:`list[SamplingParameter]` instance.
        """
        return sorted(value)


class ModelAdapterSpec(BaseModel):
    """Full identity of a model adapter — what gets persisted with a run.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * name: Registry name used to resolve the adapter implementation.
    * model_id: Provider-specific model identifier (for example ``gpt-4o``).
    * description: Optional human-readable summary for UIs and metadata tables.
    * capabilities: Static capability flags advertised by this adapter.
    * config: Opaque string key-value settings passed to the adapter constructor.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    description: str | None = None
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    config: dict[str, str] = Field(default_factory=dict[str, str])


class DatasetAdapterSpec(BaseModel):
    """Full identity of a dataset adapter."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    description: str | None = None
    row_count: int | None = Field(default=None, ge=0)
    provides: frozenset[DatasetField] = Field(
        default_factory=frozenset[DatasetField],
    )
    config: dict[str, str] = Field(default_factory=dict[str, str])

    @field_serializer("provides")
    def _serialize_provides(
        self,
        value: frozenset[DatasetField],
    ) -> list[DatasetField]:
        """
        Serialize the field for JSON export.

        :param value: Value to inspect or transform.

        :return: A :class:`list[DatasetField]` instance.
        """
        return sorted(value)


JudgeKind = Literal["single", "pairwise", "g_eval"]
"""The three concrete judge-metric shapes from ADR-0014 §3."""


class JudgeAdapterSpec(ModelAdapterSpec):
    """Specialized :class:`ModelAdapterSpec` for LLM-as-judge adapters.

    Extends the base model spec with the judge-specific contract from
    ADR-0014 §1: the judge kind, the rubric the judge scores against,
    the schema the judge must return, and a determinism flag that pins
    ``temperature=0`` plus the run's seed by default.

    * model_config: Pydantic config — frozen instance, forbid unknown fields.
    * judge_kind: Whether the judge scores one candidate, pairwise, or G-Eval style.
    * rubric: Rubric the judge applies when producing :class:`RubricScore` output.
    * response_schema_name: Pydantic schema name the judge output must deserialize to.
    * deterministic: When ``True``, pin decoding to temperature 0 and the run seed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    judge_kind: JudgeKind
    rubric: Rubric
    response_schema_name: str = "RubricScore"
    deterministic: bool = True
