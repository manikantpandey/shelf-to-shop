"""Jobs: create one per uploaded video, run the engine pipeline in the worker, keep review state."""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from engine.media.probe import MediaRejectedError
from engine.pipeline.run import Pipeline, RunResult, StageEvent
from engine.providers.errors import ProviderError
from engine.providers.fake import Scenario, fake_providers
from engine.providers.interfaces import Providers
from engine.providers.meta import meta_providers
from engine.providers.meta_client import MetaClient
from engine.runlog import CallContext, JsonlRunLog, MemoryRunLog, RunLogEntry
from engine.spend import InMemorySpendLedger, SpendCapExceededError
from shelf.config import Settings
from shelf.core.ids import uuid7
from shelf.db.models import AuditEvent, FlagRow, Job, Product, Task, Upload, Workspace
from shelf.jobs import queue
from shelf.jobs.worker import PermanentTaskError
from shelf.storage import LocalStorage

PIPELINE_TASK = "pipeline"
STAGE_ORDER = [
    "ingest",
    "detect",
    "transcribe",
    "segment",
    "enrich",
    "match",
    "verify",
    "backgrounds",
]


def create_job(db: Session, workspace: Workspace, upload: Upload, actor: str) -> Job:
    job_id = uuid7()
    job = Job(
        id=job_id,
        workspace_id=workspace.id,
        upload_id=upload.id,
        work_key=f"ws/{workspace.id}/jobs/{job_id}",
        stages={s: "waiting" for s in STAGE_ORDER},
    )
    db.add(job)
    db.flush()
    # Same transaction as the job row: a job can never exist without its task.
    queue.enqueue(db, PIPELINE_TASK, {"job_id": str(job.id)})
    db.add(
        AuditEvent(workspace_id=workspace.id, actor=actor, action="job.created", target=str(job.id))
    )
    return job


def retry_job(db: Session, job: Job, actor: str) -> None:
    job.status = "queued"
    job.error_code = None
    job.error_message = None
    queue.enqueue(db, PIPELINE_TASK, {"job_id": str(job.id)})
    db.add(
        AuditEvent(
            workspace_id=job.workspace_id, actor=actor, action="job.retried", target=str(job.id)
        )
    )


class _Tee(MemoryRunLog):
    def __init__(self, jsonl: JsonlRunLog) -> None:
        super().__init__()
        self.jsonl = jsonl

    def record(self, entry: RunLogEntry) -> None:
        super().record(entry)
        self.jsonl.record(entry)


def _providers(settings: Settings) -> tuple[Providers, MetaClient | None]:
    if settings.providers == "fake":
        return fake_providers(Scenario.load(Path(settings.fake_scenario))), None
    return meta_providers(settings.engine_config())


FRIENDLY = {
    "spend_cap": "This video would cost more than your limit. Try a shorter video.",
    "model_unavailable": "Our image and speech service is busy. Try again in a few minutes.",
    "internal": "Something went wrong while making your catalog. Try again.",
}


def run_pipeline_job(
    factory: sessionmaker[Session], settings: Settings, storage: LocalStorage, job_id: str
) -> None:
    """Worker handler. Raises PermanentTaskError on failure; the seller retries from the app."""
    with factory.begin() as db:
        job = db.get(Job, uuid.UUID(job_id))
        if job is None:
            raise PermanentTaskError(f"job {job_id} not found")
        upload = db.get(Upload, job.upload_id)
        if upload is None or upload.deleted_at is not None:
            job.status, job.error_code = "failed", "video_deleted"
            job.error_message = "The video was deleted. Record again."
            raise PermanentTaskError("upload missing")
        job.status = "running"
        video = storage.path(upload.storage_key)
        work = storage.path(job.work_key)
        workspace_id, ai_mark = str(job.workspace_id), True
        ws = db.get(Workspace, job.workspace_id)
        if ws is not None:
            ai_mark = ws.ai_mark

    def on_event(event: StageEvent) -> None:
        with factory.begin() as db:
            row = db.get(Job, uuid.UUID(job_id))
            if row is not None:
                row.stages = {**row.stages, event.stage: event.status}

    log = _Tee(JsonlRunLog(work / "runlog.jsonl"))
    ctx = CallContext(
        job_id=job_id,
        workspace_id=workspace_id,
        ledger=InMemorySpendLedger(settings.engine_config().caps),
        runlog=log,
    )
    providers, client = _providers(settings)

    async def go() -> RunResult:
        try:
            return await Pipeline(
                providers, work / "work", ctx, ai_mark=ai_mark, on_event=on_event
            ).run(video)
        finally:
            if client is not None:
                await client.aclose()

    try:
        result = asyncio.run(go())
    except Exception as exc:
        code, message = _describe(exc)
        with factory.begin() as db:
            row = db.get(Job, uuid.UUID(job_id))
            if row is not None:
                row.status, row.error_code, row.error_message = "failed", code, message
                row.cost_usd = str(_cost(log))
        raise PermanentTaskError(f"{code}: {type(exc).__name__}") from exc

    with factory.begin() as db:
        row = db.get(Job, uuid.UUID(job_id))
        if row is None:
            return
        _save_review(db, row, result, storage)
        row.status = "needs_review"
        row.cost_usd = str(_cost(log))


def _cost(log: MemoryRunLog) -> Decimal:
    return sum((e.cost_usd for e in log.entries), Decimal(0))


def _describe(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, MediaRejectedError):
        return exc.code, str(exc)
    if isinstance(exc, SpendCapExceededError):
        return "spend_cap", FRIENDLY["spend_cap"]
    if isinstance(exc, ProviderError):
        return "model_unavailable", FRIENDLY["model_unavailable"]
    return "internal", FRIENDLY["internal"]


def _save_review(db: Session, job: Job, result: RunResult, storage: LocalStorage) -> None:
    db.execute(delete(Product).where(Product.job_id == job.id))
    db.execute(delete(FlagRow).where(FlagRow.job_id == job.id))
    decisions = {d.product_idx: d for d in result.decisions}
    texts = {e.product_idx: e for e in result.enriched}
    images = {i.product_idx: i for i in result.images}
    root = storage.root
    for p in result.products:
        d, e, img = decisions.get(p.idx), texts.get(p.idx), images.get(p.idx)
        image_key = img.path.resolve().relative_to(root).as_posix() if img else None
        db.add(
            Product(
                job_id=job.id,
                workspace_id=job.workspace_id,
                idx=p.idx,
                title_en=e.title_en if e else p.description[:200],
                title_hi=e.title_hi if e else p.description[:200],
                description_en=e.description_en if e else "",
                description_hi=e.description_hi if e else "",
                price_inr=d.price_inr if d else None,
                price_source=d.source if d else "none",
                confidence=d.confidence if d else 0.0,
                evidence=[ev.model_dump(mode="json") for ev in d.evidence] if d else [],
                category=e.category if e else "other",
                colour=e.colour if e else p.colour,
                brand=e.brand if e else None,
                material=e.material if e else None,
                pattern=e.pattern if e else None,
                image_key=image_key,
                ai_background=img.ai_background if img else False,
            )
        )
    for f in result.flags:
        db.add(
            FlagRow(
                job_id=job.id,
                workspace_id=job.workspace_id,
                product_idx=f.product_idx,
                kind=f.kind,
                question_key=f.question_key,
                params=dict(f.params),
                options=list(f.options),
                candidates=list(f.candidates),
            )
        )


def open_flag_count(db: Session, job: Job) -> int:
    return len(
        db.scalars(
            select(FlagRow.id).where(FlagRow.job_id == job.id, FlagRow.status == "open")
        ).all()
    )


def pending_task_exists(db: Session, job: Job) -> bool:
    rows = db.scalars(
        select(Task).where(Task.kind == PIPELINE_TASK, Task.status.in_(["queued", "running"]))
    ).all()
    return any(t.payload.get("job_id") == str(job.id) for t in rows)
