"""The sample shop for demo sign-ins (hackathon only; demo sign-in is refused in production).

`scripts/seed_demo.py` builds one template shop from real videos. Each demo sign-in gets its own
copy: videos, items, open questions, run logs and photos, so visitors never see each other's edits.
Raw videos are not copied; the copy behaves like a shop whose videos were already deleted.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from shelf.catalog.publish import publish_shop
from shelf.config import Settings
from shelf.core.ids import uuid7
from shelf.db.models import FlagRow, Job, Product, Upload, User, Workspace
from shelf.storage import LocalStorage

_SKIP = {"id", "job_id", "workspace_id", "updated_at"}


def find_template(db: Session) -> Workspace | None:
    return db.scalar(
        select(Workspace)
        .where(Workspace.is_template.is_(True))
        .order_by(Workspace.created_at.desc())
    )


def _copy_row(row: Product | FlagRow, **changes: object) -> dict[str, object]:
    values = {c.key: getattr(row, c.key) for c in row.__table__.columns if c.key not in _SKIP}
    values.update(changes)
    return values


def clone_template(
    db: Session,
    settings: Settings,
    storage: LocalStorage,
    template: Workspace,
    user: User,
    slug: str,
) -> Workspace:
    now = datetime.now(UTC)
    ws = Workspace(
        owner_id=user.id,
        name=template.name,
        slug=slug,
        whatsapp=template.whatsapp,
        language=template.language,
        ai_mark=template.ai_mark,
        raw_retention_days=template.raw_retention_days,
        consent_account_at=now,
    )
    db.add(ws)
    db.flush()
    jobs = db.scalars(
        select(Job)
        .where(Job.workspace_id == template.id, Job.status.in_(("needs_review", "published")))
        .order_by(Job.created_at)
    ).all()
    for job in jobs:
        old_upload = db.get(Upload, job.upload_id)
        upload = Upload(
            workspace_id=ws.id,
            storage_key=f"ws/{ws.id}/uploads/{uuid7().hex}.video",
            size_bytes=old_upload.size_bytes if old_upload else 0,
            sha256=old_upload.sha256 if old_upload else "",
            container=old_upload.container if old_upload else "mp4",
            duration_s=old_upload.duration_s if old_upload else 0.0,
            deleted_at=now,
        )
        db.add(upload)
        db.flush()
        new_id = uuid7()
        work_key = f"ws/{ws.id}/jobs/{new_id}"
        src = storage.path(job.work_key)
        if src.exists():
            shutil.copytree(src, storage.path(work_key), ignore=shutil.ignore_patterns("*.wav"))
        db.add(
            Job(
                id=new_id,
                workspace_id=ws.id,
                upload_id=upload.id,
                status=job.status,
                stages=dict(job.stages),
                cost_usd=job.cost_usd,
                work_key=work_key,
                created_at=job.created_at,
            )
        )
        db.flush()
        for p in db.scalars(select(Product).where(Product.job_id == job.id)):
            key = p.image_key
            if key and key.startswith(job.work_key + "/"):
                key = work_key + key[len(job.work_key) :]
            db.add(Product(**_copy_row(p, image_key=key), job_id=new_id, workspace_id=ws.id))
        for f in db.scalars(select(FlagRow).where(FlagRow.job_id == job.id)):
            db.add(FlagRow(**_copy_row(f), job_id=new_id, workspace_id=ws.id))
        db.flush()
    if ws.whatsapp and any(j.status == "published" for j in jobs):
        publish_shop(db, settings, storage, ws, user)
    return ws
