"""Keeping only what is needed, for as long as it is needed (DPDP Act: storage limitation).

Runs every hour in the worker:
- Shop videos and everything cut from them that may show people (the normalised video, its
  audio, sampled frames, the frames behind each cut-out, the moments a seller browsed) are deleted
  after the shop's retention period (Settings, default 7 days). Item photos, prices and
  transcripts stay.
- Uploads that never finished are deleted after a day.
- Customer names and notes on orders are cleared after ORDER_DETAIL_DAYS; totals and items stay.
- Ended sessions are removed a month after they end.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, sessionmaker

from shelf.core.logging import get_logger
from shelf.db.models import Job, Order, SessionRow, Upload, Workspace
from shelf.storage import LocalStorage

log = get_logger(__name__)
ORDER_DETAIL_DAYS = 90
ABANDONED_UPLOAD_HOURS = 24
SWEEP_EVERY_S = 3600


def _naive(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def _drop_media(storage: LocalStorage, job: Job) -> None:
    """Remove the parts of a job that may show people; keep item photos and the run log."""
    work = storage.path(job.work_key)
    storage.delete(f"{job.work_key}/work/ingest")
    storage.delete(f"{job.work_key}/moments")
    segment = work / "work" / "segment"
    if segment.exists():
        for frame in segment.glob("frame_*.jpg"):
            frame.unlink(missing_ok=True)


def sweep(db: Session, storage: LocalStorage, now: datetime | None = None) -> dict[str, int]:
    now = _naive(now or datetime.now(UTC))
    counts = {"videos": 0, "abandoned": 0, "orders": 0, "sessions": 0}

    # Videos past each shop's retention period.
    rows = db.execute(
        select(Upload, Workspace.raw_retention_days)
        .join(Workspace, Workspace.id == Upload.workspace_id)
        .where(Upload.deleted_at.is_(None), Upload.status == "ready")
    ).all()
    for upload, days in rows:
        if _naive(upload.created_at) > now - timedelta(days=days):
            continue
        storage.delete(upload.storage_key)
        for job in db.scalars(select(Job).where(Job.upload_id == upload.id)):
            _drop_media(storage, job)
        upload.deleted_at = now
        counts["videos"] += 1

    # Uploads that stopped half way and were never finished.
    stale = now - timedelta(hours=ABANDONED_UPLOAD_HOURS)
    for upload in db.scalars(
        select(Upload).where(
            Upload.deleted_at.is_(None),
            Upload.status.in_(("receiving", "rejected")),
            Upload.created_at < stale,
        )
    ):
        storage.delete(upload.storage_key)
        upload.deleted_at = now
        counts["abandoned"] += 1

    # Customer details on old orders.
    old = now - timedelta(days=ORDER_DETAIL_DAYS)
    for order in db.scalars(
        select(Order).where(
            Order.created_at < old,
            or_(Order.customer_name.is_not(None), Order.note.is_not(None)),
        )
    ):
        order.customer_name = None
        order.note = None
        counts["orders"] += 1

    gone = now - timedelta(days=30)
    result = db.execute(
        delete(SessionRow).where(or_(SessionRow.expires_at < gone, SessionRow.revoked_at < gone))
    )
    counts["sessions"] = int(getattr(result, "rowcount", 0) or 0)
    return counts


class Sweeper:
    """Runs `sweep` every hour on a background thread until stopped."""

    def __init__(self, factory: sessionmaker[Session], storage: LocalStorage) -> None:
        self.factory = factory
        self.storage = storage
        self._stop = threading.Event()

    def run_once(self) -> dict[str, Any]:
        with self.factory.begin() as db:
            counts = sweep(db, self.storage)
        if any(counts.values()):
            log.info("retention_sweep", **counts)
        return counts

    def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                log.exception("retention_sweep_failed")
            self._stop.wait(SWEEP_EVERY_S)

    def start(self) -> None:
        threading.Thread(target=self.run_forever, name="retention-sweeper", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
