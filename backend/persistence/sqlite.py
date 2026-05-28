"""SQLite-backed concrete :class:`StorageAdapter`.

Every public method maps one-to-one onto an ADR-0006 §5 transaction
boundary: ``create_run`` is one transaction; each
``append_sample`` / ``append_metric_result`` pair is its own short
transaction; ``finalize_run`` updates the row + writes the telemetry
report in one transaction.

# ADR: Persistence — SQLite Default, Postgres Swap-In
# See: adr/0006-persistence-sqlite-default-postgres-swap-in.md
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.contracts.adapter_spec import (
    DatasetAdapterSpec,
    ModelAdapterSpec,
    ModelCapabilities,
)
from backend.contracts.metric_result import MetricResult, MetricSpec
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
    EngineConfig,
    EngineKind,
    EvaluationSample,
    GenerationResponse,
)
from backend.contracts.run import EvaluationRunRequest, EvaluationRunResult
from backend.contracts.telemetry import TelemetryReport
from backend.observability import get_logger
from backend.persistence.base import redact_secrets
from backend.persistence.orm import (
    Base,
    DatasetMetadata,
    ModelMetadata,
    Run,
    RunTelemetry,
    Sample,
)
from backend.persistence.orm import MetricResult as MetricResultORM
from backend.persistence.session import create_async_engine_for, create_session_factory

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession


logger = get_logger(__name__)


def _redact_spec_json(spec_dump: dict[str, Any]) -> str:
    """
    Redact spec json.

    :param spec_dump: The spec dump.

    :return: The str result.
    """
    return json.dumps(redact_secrets(spec_dump), sort_keys=True)


class SQLiteStorage:
    """Async SQLite storage adapter (also works against any SQLAlchemy URL).

    The class satisfies :class:`StorageAdapter` structurally. The name is
    kept for backwards-compatibility with the ADR; the only SQLite-specific
    behavior lives in the pragma installer that
    :mod:`backend.persistence.session` attaches when the URL points at SQLite.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        session_factory: Callable[[], AsyncSession] | None = None,
    ) -> None:
        """
        Bind to an :class:`AsyncEngine` and prepare the session factory.

        :param engine: SQLAlchemy async engine.
        :param session_factory: Async session factory bound to ``engine``.
        """
        self._engine = engine
        self._session_factory = session_factory or create_session_factory(engine)

    @classmethod
    def from_url(cls, url: str, *, echo: bool = False) -> SQLiteStorage:
        """
        Construct a storage adapter directly from a SQLAlchemy URL.

        :param url: Database connection URL.
        :param echo: Whether SQLAlchemy should echo SQL statements.

        :return: :class:`SQLiteStorage` instance.
        """
        engine = create_async_engine_for(url, echo=echo)
        return cls(engine)

    @property
    def engine(self) -> AsyncEngine:
        """
        Expose the underlying engine — used by Alembic only.

        :return: :class:`AsyncEngine` instance.
        """
        return self._engine

    async def create_all(self) -> None:
        """
        Create every ORM table — convenience wrapper for tests / dev.

        Production code uses Alembic migrations instead; this helper is intentionally idempotent
        so the in-memory test fixture can call it once at session startup.
        """
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        """Dispose of the underlying engine."""
        await self._engine.dispose()

    # ---------- Runs ----------

    async def create_run(self, request: EvaluationRunRequest) -> RunRecord:
        """
        Persist a new ``runs`` row in :class:`RunStatus.PENDING` state.

        :param request: Evaluation run request payload.

        :return: :class:`RunRecord` instance.
        """
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            run = Run(
                id=request.run_id,
                title=request.title,
                description=request.description,
                created_at=now,
                finished_at=None,
                status=RunStatus.PENDING.value,
                engine_kind=request.engine.kind,
                seed=request.seed,
                model_spec_json=_redact_spec_json(request.model.model_dump()),
                dataset_spec_json=_redact_spec_json(request.dataset.model_dump()),
                metric_specs_json=json.dumps(
                    [m.model_dump() for m in request.metrics],
                    sort_keys=True,
                ),
                summary_json=None,
            )
            session.add(run)
            await session.commit()
        return RunRecord(
            id=request.run_id,
            title=request.title,
            description=request.description,
            created_at=now,
            finished_at=None,
            status=RunStatus.PENDING,
            engine_kind=request.engine.kind,
            model_spec=request.model,
            dataset_spec=request.dataset,
            metric_specs=list(request.metrics),
            seed=request.seed,
        )

    async def append_sample(self, run_id: str, sample: SampleRecord) -> None:
        """
        Append a row to ``samples``.

        :param run_id: Unique run identifier.
        :param sample: Evaluation sample being processed.
        """
        async with self._session_factory() as session:
            row = Sample(
                run_id=run_id,
                idx=sample.idx,
                input=sample.input,
                reference=sample.reference,
                generation=sample.generation,
                latency_ms=sample.latency_ms,
                error=sample.error,
            )
            session.add(row)
            await session.commit()

    async def append_metric_result(
        self,
        run_id: str,
        result: MetricResultRecord,
    ) -> None:
        """
        Append a row to ``metric_results``.

        :param run_id: Unique run identifier.
        :param result: Metric result record to persist.
        """
        async with self._session_factory() as session:
            row = MetricResultORM(
                run_id=run_id,
                sample_idx=result.sample_idx,
                metric_name=result.metric_name,
                metric_version=result.metric_version,
                status=result.status.value,
                value=result.value,
                sub_values_json=(json.dumps([s.model_dump() for s in result.sub_values]) if result.sub_values else None),
                compute_latency_ms=result.compute_latency_ms,
                exception_class=result.exception_class,
                exception_message=result.exception_message,
            )
            session.add(row)
            await session.commit()

    async def finalize_run(
        self,
        run_id: str,
        summary: RunSummary,
        telemetry: TelemetryReport,
    ) -> EvaluationRunResult:
        """
        Mark the run finished, persist summary + telemetry, return result.

        :param run_id: Unique run identifier.
        :param summary: Run summary metadata.
        :param telemetry: Telemetry report for the run.

        :return: :class:`~backend.contracts.run.EvaluationRunResult`.
        """
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise KeyError(f"run {run_id!r} not found")
            had_errors = summary.error_count > 0
            run.status = RunStatus.PARTIAL.value if had_errors else RunStatus.SUCCEEDED.value
            run.finished_at = now
            run.summary_json = json.dumps(summary.model_dump(), sort_keys=True)
            telem = RunTelemetry(
                run_id=run_id,
                report_json=json.dumps(telemetry.model_dump(mode="json"), sort_keys=True),
            )
            session.add(telem)
            await session.commit()
        return await self.get_run(run_id)

    async def get_run(self, run_id: str) -> EvaluationRunResult:
        """
        Hydrate a complete :class:`EvaluationRunResult` from the database.

        :param run_id: Unique run identifier.

        :return: :class:`~backend.contracts.run.EvaluationRunResult`.
        """
        async with self._session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None:
                raise KeyError(f"run {run_id!r} not found")
            samples_orm = await self._load_samples(session, run_id)
            metric_orm = await self._load_metric_results(session, run_id)
            telemetry_orm = await session.get(RunTelemetry, run_id)

        request = self._rehydrate_request(run)
        samples_pyd, generations = self._project_samples(samples_orm)
        per_sample, aggregate = self._project_metric_results(metric_orm)
        telemetry = self._project_telemetry(telemetry_orm, run)
        status_literal = self._status_literal(run.status)

        return EvaluationRunResult(
            run_id=run_id,
            status=status_literal,
            started_at=run.created_at,
            finished_at=run.finished_at or run.created_at,
            request=request,
            samples=samples_pyd,
            generations=generations,
            metric_results=per_sample,
            aggregate_metric_results=aggregate,
            telemetry=telemetry,
            error=None,
        )

    async def list_runs(self, query: RunQuery) -> RunListPage:
        """
        Filter / paginate ``runs`` according to ``query``.

        :param query: Pagination and filter query for listing runs.

        :return: :class:`RunListPage` instance.
        """
        async with self._session_factory() as session:
            stmt = select(Run)
            count_stmt = select(func.count()).select_from(Run)
            if query.status is not None:
                stmt = stmt.where(Run.status == query.status.value)
                count_stmt = count_stmt.where(Run.status == query.status.value)
            if query.engine_kind is not None:
                stmt = stmt.where(Run.engine_kind == query.engine_kind)
                count_stmt = count_stmt.where(Run.engine_kind == query.engine_kind)
            if query.created_after is not None:
                stmt = stmt.where(Run.created_at >= query.created_after)
                count_stmt = count_stmt.where(Run.created_at >= query.created_after)
            if query.created_before is not None:
                stmt = stmt.where(Run.created_at <= query.created_before)
                count_stmt = count_stmt.where(Run.created_at <= query.created_before)
            if query.text is not None:
                like = f"%{query.text}%"
                stmt = stmt.where(Run.title.like(like))
                count_stmt = count_stmt.where(Run.title.like(like))

            offset = (query.page - 1) * query.limit
            stmt = stmt.order_by(Run.created_at.desc()).offset(offset).limit(query.limit)

            rows = (await session.execute(stmt)).scalars().all()
            total = (await session.execute(count_stmt)).scalar_one()

        items = [self._rehydrate_run_record(row) for row in rows]
        return RunListPage(
            items=items,
            page=query.page,
            limit=query.limit,
            total=int(total),
        )

    async def delete_run(self, run_id: str) -> None:
        """
        Remove a run and its descendants.

        :param run_id: Unique run identifier.
        """
        async with self._session_factory() as session:
            await session.execute(delete(Run).where(Run.id == run_id))
            await session.commit()

    # ---------- Metadata ----------

    async def upsert_model_metadata(self, meta: ModelMetadataRecord) -> None:
        """
        Insert / update a row in ``model_metadata``.

        :param meta: Model or dataset metadata record to upsert.
        """
        async with self._session_factory() as session:
            existing = await session.get(ModelMetadata, meta.id)
            if existing is None:
                session.add(
                    ModelMetadata(
                        id=meta.id,
                        name=meta.name,
                        capabilities_json=json.dumps(
                            meta.capabilities.model_dump(),
                            sort_keys=True,
                        ),
                        description=meta.description,
                        last_seen_at=meta.last_seen_at,
                    ),
                )
            else:
                existing.name = meta.name
                existing.capabilities_json = json.dumps(
                    meta.capabilities.model_dump(),
                    sort_keys=True,
                )
                existing.description = meta.description
                existing.last_seen_at = meta.last_seen_at
            await session.commit()

    async def upsert_dataset_metadata(self, meta: DatasetMetadataRecord) -> None:
        """
        Insert / update a row in ``dataset_metadata``.

        :param meta: Model or dataset metadata record to upsert.
        """
        async with self._session_factory() as session:
            existing = await session.get(DatasetMetadata, meta.id)
            if existing is None:
                session.add(
                    DatasetMetadata(
                        id=meta.id,
                        name=meta.name,
                        row_count=meta.row_count,
                        description=meta.description,
                        last_seen_at=meta.last_seen_at,
                    ),
                )
            else:
                existing.name = meta.name
                existing.row_count = meta.row_count
                existing.description = meta.description
                existing.last_seen_at = meta.last_seen_at
            await session.commit()

    async def list_model_metadata(self) -> list[ModelMetadataRecord]:
        """
        Return every cached :class:`ModelMetadataRecord` row.

        :return: :class:`ModelMetadataRecord` instance.
        """
        async with self._session_factory() as session:
            rows = (await session.execute(select(ModelMetadata))).scalars().all()
        return [
            ModelMetadataRecord(
                id=row.id,
                name=row.name,
                capabilities=ModelCapabilities.model_validate(
                    json.loads(row.capabilities_json),
                ),
                description=row.description,
                last_seen_at=row.last_seen_at,
            )
            for row in rows
        ]

    async def list_dataset_metadata(self) -> list[DatasetMetadataRecord]:
        """
        Return every cached :class:`DatasetMetadataRecord` row.

        :return: :class:`DatasetMetadataRecord` instance.
        """
        async with self._session_factory() as session:
            rows = (await session.execute(select(DatasetMetadata))).scalars().all()
        return [
            DatasetMetadataRecord(
                id=row.id,
                name=row.name,
                row_count=row.row_count,
                description=row.description,
                last_seen_at=row.last_seen_at,
            )
            for row in rows
        ]

    # ---------- Internals ----------

    async def _load_samples(
        self,
        session: AsyncSession,
        run_id: str,
    ) -> list[Sample]:
        """
        Load related rows for persistence rehydration.

        :param session: The session.
        :param run_id: Unique run identifier.

        :return: A :class:`list[Sample]` instance.
        """
        stmt = select(Sample).where(Sample.run_id == run_id).order_by(Sample.idx)
        return list((await session.execute(stmt)).scalars().all())

    async def _load_metric_results(
        self,
        session: AsyncSession,
        run_id: str,
    ) -> list[MetricResultORM]:
        """
        Load related rows for persistence rehydration.

        :param session: The session.
        :param run_id: Unique run identifier.

        :return: A :class:`list[MetricResultORM]` instance.
        """
        stmt = select(MetricResultORM).where(MetricResultORM.run_id == run_id).order_by(MetricResultORM.id)
        return list((await session.execute(stmt)).scalars().all())

    def _rehydrate_request(self, run: Run) -> EvaluationRunRequest:
        """
        Rehydrate a contract ``request`` from stored rows.

        :param run: ORM run row to project into contract models.

        :return: A :class:`EvaluationRunRequest` instance.
        """
        model_spec = ModelAdapterSpec.model_validate(json.loads(run.model_spec_json))
        dataset_spec = DatasetAdapterSpec.model_validate(
            json.loads(run.dataset_spec_json),
        )
        metric_specs_raw = cast("list[Any]", json.loads(run.metric_specs_json))
        metrics = [MetricSpec.model_validate(m) for m in metric_specs_raw]
        engine_kind: EngineKind = cast("EngineKind", run.engine_kind)
        return EvaluationRunRequest(
            run_id=run.id,
            title=run.title,
            description=run.description,
            seed=run.seed,
            model=model_spec,
            dataset=dataset_spec,
            metrics=metrics,
            engine=EngineConfig(kind=engine_kind),
        )

    def _project_samples(
        self,
        samples: list[Sample],
    ) -> tuple[list[EvaluationSample], list[GenerationResponse]]:
        """
        Project ORM rows into contract ``samples`` records.

        :param samples: The samples.

        :return: A :class:`tuple[list[EvaluationSample], list[GenerationResponse]]` instance.
        """
        eval_samples: list[EvaluationSample] = []
        generations: list[GenerationResponse] = []
        for s in samples:
            eval_samples.append(
                EvaluationSample(
                    idx=s.idx,
                    input=s.input,
                    reference=s.reference,
                ),
            )
            generations.append(
                GenerationResponse(
                    text=s.generation or "",
                    latency_ms=s.latency_ms,
                ),
            )
        return eval_samples, generations

    def _project_metric_results(
        self,
        rows: list[MetricResultORM],
    ) -> tuple[list[MetricResult], list[MetricResult]]:
        """
        Project ORM rows into contract ``metric_results`` records.

        :param rows: The rows.

        :return: A :class:`tuple[list[MetricResult], list[MetricResult]]` instance.
        """
        per_sample: list[MetricResult] = []
        aggregate: list[MetricResult] = []
        for row in rows:
            sub_values_payload: list[Any] = cast("list[Any]", json.loads(row.sub_values_json)) if row.sub_values_json else []
            metric_result = MetricResult.model_validate(
                {
                    "metric_name": row.metric_name,
                    "metric_version": row.metric_version,
                    "status": row.status,
                    "value": row.value,
                    "sub_values": sub_values_payload,
                    "compute_latency_ms": row.compute_latency_ms,
                    "sample_idx": row.sample_idx,
                    "exception_class": row.exception_class,
                    "exception_message": row.exception_message,
                },
            )
            if row.sample_idx is None:
                aggregate.append(metric_result)
            else:
                per_sample.append(metric_result)
        return per_sample, aggregate

    def _project_telemetry(
        self,
        telemetry_row: RunTelemetry | None,
        run: Run,
    ) -> TelemetryReport:
        """
        Project ORM rows into contract ``telemetry`` records.

        :param telemetry_row: The telemetry row.
        :param run: ORM run row to project into contract models.

        :return: A :class:`TelemetryReport` instance.
        """
        if telemetry_row is None:
            finished_at = run.finished_at or run.created_at
            return TelemetryReport(
                run_id=run.id,
                started_at=run.created_at,
                finished_at=finished_at,
                total_duration_ms=(finished_at - run.created_at).total_seconds() * 1000.0,
            )
        return TelemetryReport.model_validate(json.loads(telemetry_row.report_json))

    def _rehydrate_run_record(self, run: Run) -> RunRecord:
        """
        Rehydrate a contract ``run_record`` from stored rows.

        :param run: ORM run row to project into contract models.

        :return: A :class:`RunRecord` instance.
        """
        return RunRecord(
            id=run.id,
            title=run.title,
            description=run.description,
            created_at=run.created_at,
            finished_at=run.finished_at,
            status=RunStatus(run.status),
            engine_kind=cast("EngineKind", run.engine_kind),
            model_spec=ModelAdapterSpec.model_validate(
                json.loads(run.model_spec_json),
            ),
            dataset_spec=DatasetAdapterSpec.model_validate(
                json.loads(run.dataset_spec_json),
            ),
            metric_specs=[MetricSpec.model_validate(m) for m in cast("list[Any]", json.loads(run.metric_specs_json))],
            seed=run.seed,
        )

    def _status_literal(
        self,
        status_str: str,
    ) -> Any:  # — narrow Literal returned to caller.
        """
        Map a status label to the engine literal type.

        :param status_str: The status str.

        :return: A :class:`Any` instance.
        """
        if status_str == RunStatus.SUCCEEDED.value:
            return "succeeded"
        if status_str == RunStatus.PARTIAL.value:
            return "partial"
        if status_str == RunStatus.FAILED.value:
            return "failed"
        if status_str == RunStatus.CANCELLED.value:
            return "cancelled"
        # PENDING / RUNNING runs are not supposed to be returned via
        # get_run as a finalized result — but we surface them as
        # 'failed' to keep the literal valid for in-flight diagnostics.
        return "failed"
