"""Storage Protocol + secrets redaction.

# ADR: Persistence — SQLite Default, Postgres Swap-In
# See: adr/0006-persistence-sqlite-default-postgres-swap-in.md
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Protocol, cast, runtime_checkable

if TYPE_CHECKING:
    from aef.contracts.persistence import (
        DatasetMetadataRecord,
        MetricResultRecord,
        ModelMetadataRecord,
        RunListPage,
        RunQuery,
        RunRecord,
        RunSummary,
        SampleRecord,
    )
    from aef.contracts.run import EvaluationRunRequest, EvaluationRunResult
    from aef.contracts.telemetry import TelemetryReport


# Per ADR-0006 §8 / ADR-0012 §8 — sensitive field-name allow-list.
# We match an exact normalized form of the key against this set;
# ``max_tokens`` does NOT match (plural; the token ``tokens`` is not in
# the list) and ``tokenizer_path`` does not match (compound noun where
# ``token`` is only a prefix). Common compound forms like
# ``OpenAI_Api_Key`` or ``oauth_token`` ARE matched because their
# trailing token equals one of the entries below.
SENSITIVE_FIELD_TOKENS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "secret",
        "token",
        "password",
        "credential",
        "authorization",
        "bearer",
    },
)
REDACTED_PLACEHOLDER = "<redacted>"

# Splits camelCase, kebab-case, snake_case, and dotted-case into
# canonical lower-cased segments. ``OpenAIApiKey`` -> ``open ai api key``.
_SPLITTER = re.compile(r"[_\-\s\.]+|(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def redact_secrets(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-copy of ``payload`` with secret-like values redacted.

    Keys whose name (case-insensitive) contains any substring in
    :data:`SENSITIVE_FIELD_SUBSTRINGS` are replaced with the redaction
    placeholder. Nested dicts and lists are walked recursively.

    The function is intentionally conservative — it never mutates the
    original payload, and it prefers false positives (over-redacting)
    to under-redacting, since the cost of leaking a secret outweighs
    the cost of redacting one too many fields.
    """
    return _redact(payload)


def _redact(value: Any) -> Any:  # — heterogeneous JSON payload.
    if isinstance(value, dict):
        value_dict = cast("dict[Any, Any]", value)
        out: dict[str, Any] = {}
        for key, sub in value_dict.items():
            key_str = str(key)
            if _is_sensitive(key_str):
                out[key_str] = REDACTED_PLACEHOLDER
            else:
                out[key_str] = _redact(sub)
        return out
    if isinstance(value, list):
        value_list = cast("list[Any]", value)
        return [_redact(item) for item in value_list]
    return value


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    if lowered in SENSITIVE_FIELD_TOKENS:
        return True
    parts = [p.lower() for p in _SPLITTER.split(key) if p]
    if not parts:
        return False
    last = parts[-1]
    if last in SENSITIVE_FIELD_TOKENS:
        return True
    # Two-word combos like ``api key`` (joined trailing pair).
    return len(parts) >= 2 and f"{parts[-2]}_{last}" in SENSITIVE_FIELD_TOKENS


@runtime_checkable
class StorageAdapter(Protocol):
    """The persistence Protocol every storage backend implements.

    The contract is the only seam between the engine / API / CLI and the
    database. Implementations return Pydantic record instances —
    callers never see ORM objects.
    """

    async def create_run(self, request: EvaluationRunRequest) -> RunRecord:
        """Persist a new ``runs`` row in :attr:`RunStatus.PENDING` state."""
        ...

    async def append_sample(self, run_id: str, sample: SampleRecord) -> None:
        """Append a sample row to ``samples``."""
        ...

    async def append_metric_result(
        self,
        run_id: str,
        result: MetricResultRecord,
    ) -> None:
        """Append a row to ``metric_results``."""
        ...

    async def finalize_run(
        self,
        run_id: str,
        summary: RunSummary,
        telemetry: TelemetryReport,
    ) -> EvaluationRunResult:
        """Mark a run as finished, store its summary + telemetry."""
        ...

    async def get_run(self, run_id: str) -> EvaluationRunResult:
        """Retrieve the fully-populated :class:`EvaluationRunResult`."""
        ...

    async def list_runs(self, query: RunQuery) -> RunListPage:
        """Page through stored runs filtered by ``query``."""
        ...

    async def delete_run(self, run_id: str) -> None:
        """Remove a run and its descendants (samples, metric_results, telemetry)."""
        ...

    async def upsert_model_metadata(self, meta: ModelMetadataRecord) -> None:
        """Upsert a row in ``model_metadata``."""
        ...

    async def upsert_dataset_metadata(self, meta: DatasetMetadataRecord) -> None:
        """Upsert a row in ``dataset_metadata``."""
        ...

    async def list_model_metadata(self) -> list[ModelMetadataRecord]:
        """Return every cached :class:`ModelMetadataRecord` row."""
        ...

    async def list_dataset_metadata(self) -> list[DatasetMetadataRecord]:
        """Return every cached :class:`DatasetMetadataRecord` row."""
        ...
