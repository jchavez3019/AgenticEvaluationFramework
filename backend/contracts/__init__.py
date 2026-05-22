"""Pydantic v2 contracts that cross every module boundary in the framework.

Every public function signature, every API request/response, every adapter
method, and every persisted record is typed against a model defined here.
``Dict[str, Any]`` is forbidden on public surfaces (per ADR-0010); nested
dictionaries are promoted to typed sub-models.

The module split is acyclic by design:

- :mod:`backend.contracts.primitives` — leaf shapes (chat, generation,
  sample, judge, engine, output) with no sibling imports.
- :mod:`backend.contracts.adapter_spec` — adapter specs (depends on
  primitives).
- :mod:`backend.contracts.metric_result` — metric shapes (depends on
  primitives + adapter_spec).
- :mod:`backend.contracts.telemetry` — telemetry shapes (depends on
  primitives).
- :mod:`backend.contracts.run` — top-level run request/result (depends on
  every other module above).
- :mod:`backend.contracts.persistence` — record models for
  :class:`StorageAdapter` (depends on the layers above).

# ADR: Adapter Architecture for Models and Datasets
# See: adr/0003-adapter-architecture-for-models-and-datasets.md
"""

from __future__ import annotations

from backend.contracts.adapter_spec import (
    CostReporting,
    DatasetAdapterSpec,
    DatasetField,
    JudgeAdapterSpec,
    JudgeKind,
    ModelAdapterSpec,
    ModelCapabilities,
    ModelFamily,
    SamplingParameter,
)
from backend.contracts.metric_result import (
    MetricApplicability,
    MetricInputs,
    MetricKind,
    MetricRequiredInput,
    MetricResult,
    MetricSpec,
    MetricStatus,
    SubScore,
)
from backend.contracts.persistence import (
    DatasetMetadataRecord,
    MetricResultRecord,
    ModelMetadataRecord,
    RunListPage,
    RunQuery,
    RunRecord,
    RunStatus,
    RunSummary,
    SampleRecord,
)
from backend.contracts.primitives import (
    BiasMitigation,
    ChatMessage,
    ChatRole,
    CriterionScore,
    EngineConfig,
    EngineKind,
    EngineQueueConfig,
    EngineQueueName,
    EvaluationSample,
    GenerationConfig,
    GenerationRequest,
    GenerationResponse,
    JudgmentRequest,
    JudgmentResponse,
    OutputConfig,
    PairwisePreference,
    PipelineStage,
    RetrievedChunk,
    Rubric,
    RubricAggregation,
    RubricCriterion,
    RubricScale,
    RubricScore,
    SampleMetadata,
    Usage,
)
from backend.contracts.run import EvaluationRunRequest, EvaluationRunResult
from backend.contracts.telemetry import (
    QueueDepthSample,
    StageSummary,
    TelemetryReport,
    ThroughputCounters,
    TimingRecord,
)

__all__ = [
    "BiasMitigation",
    "ChatMessage",
    "ChatRole",
    "CostReporting",
    "CriterionScore",
    "DatasetAdapterSpec",
    "DatasetField",
    "DatasetMetadataRecord",
    "EngineConfig",
    "EngineKind",
    "EngineQueueConfig",
    "EngineQueueName",
    "EvaluationRunRequest",
    "EvaluationRunResult",
    "EvaluationSample",
    "GenerationConfig",
    "GenerationRequest",
    "GenerationResponse",
    "JudgeAdapterSpec",
    "JudgeKind",
    "JudgmentRequest",
    "JudgmentResponse",
    "MetricApplicability",
    "MetricInputs",
    "MetricKind",
    "MetricRequiredInput",
    "MetricResult",
    "MetricResultRecord",
    "MetricSpec",
    "MetricStatus",
    "ModelAdapterSpec",
    "ModelCapabilities",
    "ModelFamily",
    "ModelMetadataRecord",
    "OutputConfig",
    "PairwisePreference",
    "PipelineStage",
    "QueueDepthSample",
    "RetrievedChunk",
    "Rubric",
    "RubricAggregation",
    "RubricCriterion",
    "RubricScale",
    "RubricScore",
    "RunListPage",
    "RunQuery",
    "RunRecord",
    "RunStatus",
    "RunSummary",
    "SampleMetadata",
    "SampleRecord",
    "SamplingParameter",
    "StageSummary",
    "SubScore",
    "TelemetryReport",
    "ThroughputCounters",
    "TimingRecord",
    "Usage",
]
