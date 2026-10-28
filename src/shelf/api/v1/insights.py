"""The seller's home screen data: shop numbers, video history and how each video was read.

Run details come from the job's own run log and stage events, so the seller can see which model
did what, how long it took, what it cost, and the evidence behind every price.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path, PureWindowsPath
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shelf.api.deps import SessionDep, SettingsDep
from shelf.auth.sessions import SellerDep
from shelf.catalog.publish import item_id, live_products
from shelf.core.clock import india_today, iso_utc
from shelf.core.errors import AppError
from shelf.db.models import Catalog, FlagRow, Job, Product, ShopCounter, Upload, Workspace
from shelf.jobs.service import STAGE_ORDER
from shelf.storage import LocalStorage

router = APIRouter()
DAYS = 7


def shop_today() -> date:
    return india_today()


def _storage(request: Request) -> LocalStorage:
    storage: LocalStorage = request.app.state.storage
    return storage


def _job(db: Session, workspace: Workspace, job_id: uuid.UUID) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id, Job.workspace_id == workspace.id))
    if job is None:
        raise AppError("not_found", "That video does not exist.", status=404)
    return job


_FRAME_NAME = re.compile(r"^frame_\d{2}_\d\.jpg$")


def cut_frames(work: Path) -> dict[int, Path]:
    """The video frame each item's photo was cut from (by file name; paths may point elsewhere
    when the job was copied from the sample shop)."""
    seg = work / "work" / "segment"
    found: dict[int, Path] = {}
    try:
        doc = json.loads((work / "work" / "stages" / "segment.json").read_text(encoding="utf-8"))
        for cut in doc.get("output", {}).get("cutouts", []):
            name = PureWindowsPath(str(cut.get("frame", ""))).name
            if _FRAME_NAME.match(name) and (seg / name).exists():
                found[int(cut["product_idx"])] = seg / name
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    for path in sorted(seg.glob("frame_*_0.jpg")) if seg.exists() else []:
        idx = int(path.name[6:8])
        found.setdefault(idx, path)
    return found


@router.get("/stats", tags=["insights"])
def stats(seller: SellerDep, db: SessionDep, settings: SettingsDep) -> dict[str, Any]:
    from shelf.api.v1.shop import order_summary  # shop.py imports this module

    ws = seller.workspace
    today = shop_today()
    since = today - timedelta(days=DAYS - 1)
    counters = db.scalars(
        select(ShopCounter).where(ShopCounter.workspace_id == ws.id, ShopCounter.day >= since)
    ).all()
    per_day: dict[date, dict[str, int]] = defaultdict(lambda: {"view": 0, "order": 0})
    orders_by_item: dict[str, int] = defaultdict(int)
    for c in counters:
        per_day[c.day][c.kind] += c.count
        if c.kind == "order" and c.item_id:
            orders_by_item[c.item_id] += c.count
    days = [since + timedelta(days=i) for i in range(DAYS)]

    live = [p for p in live_products(db, ws) if p.price_inr and p.image_key]
    titles = {item_id(ws.slug, p): p.title_en for p in live}
    top = sorted(
        ((iid, n) for iid, n in orders_by_item.items() if iid in titles),
        key=lambda pair: pair[1],
        reverse=True,
    )[:5]
    jobs = db.scalars(select(Job).where(Job.workspace_id == ws.id, Job.kind == "video")).all()
    open_flags = db.scalar(
        select(func.count())
        .select_from(FlagRow)
        .join(Job, Job.id == FlagRow.job_id)
        .where(
            FlagRow.workspace_id == ws.id, FlagRow.status == "open", Job.status == "needs_review"
        )
    )
    latest = db.scalar(
        select(Catalog)
        .where(Catalog.workspace_id == ws.id)
        .order_by(Catalog.version.desc())
        .limit(1)
    )
    return {
        "items_live": sum(1 for p in live if not p.sold_out),
        "items_sold_out": sum(1 for p in live if p.sold_out),
        "views_7d": sum(per_day[d]["view"] for d in days),
        "orders_7d": sum(per_day[d]["order"] for d in days),
        "by_day": [
            {"day": d.isoformat(), "views": per_day[d]["view"], "orders": per_day[d]["order"]}
            for d in days
        ],
        "top_items": [{"id": iid, "title": titles[iid], "orders": n} for iid, n in top],
        "videos": len(jobs),
        "videos_to_check": sum(1 for j in jobs if j.status == "needs_review"),
        "videos_processing": sum(1 for j in jobs if j.status in ("queued", "running")),
        "questions_open": open_flags or 0,
        "spend_usd": str(sum((Decimal(j.cost_usd) for j in jobs), Decimal(0))),
        "shop_url": f"{settings.public_base_url}/s/{ws.slug}" if latest else None,
        "published_at": iso_utc(latest.created_at) if latest else None,
        "orders": order_summary(db, ws),
    }


@router.get("/videos", tags=["insights"])
def video_history(seller: SellerDep, db: SessionDep) -> dict[str, Any]:
    jobs = db.scalars(
        select(Job)
        .where(Job.workspace_id == seller.workspace.id, Job.kind == "video")
        .order_by(Job.created_at.desc())
        .limit(50)
    ).all()
    out = []
    for job in jobs:
        products = db.scalars(
            select(Product)
            .where(Product.job_id == job.id, Product.removed.is_(False))
            .order_by(Product.idx)
        ).all()
        upload = db.get(Upload, job.upload_id)
        thumb = next((p for p in products if p.image_key), None)
        open_flags = db.scalar(
            select(func.count())
            .select_from(FlagRow)
            .where(FlagRow.job_id == job.id, FlagRow.status == "open")
        )
        out.append(
            {
                "id": str(job.id),
                "status": job.status,
                "created_at": iso_utc(job.created_at),
                "duration_s": round(upload.duration_s, 1) if upload else None,
                "items": len(products),
                "titles": [p.title_en for p in products[:3]],
                "open_flags": open_flags or 0,
                "cost_usd": job.cost_usd,
                "thumb_url": f"/api/v1/jobs/{job.id}/images/{thumb.idx}" if thumb else None,
                "error_message": job.error_message,
            }
        )
    return {"videos": out}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _when(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


@router.get("/jobs/{job_id}/details", tags=["insights"])
def job_details(
    job_id: uuid.UUID, request: Request, seller: SellerDep, db: SessionDep
) -> dict[str, Any]:
    job = _job(db, seller.workspace, job_id)
    work = _storage(request).path(job.work_key)
    calls = _read_jsonl(work / "runlog.jsonl")
    events = _read_jsonl(work / "work" / "events.jsonl")

    started: dict[str, datetime] = {}
    finished: dict[str, datetime] = {}
    for e in events:
        at = _when(e.get("at"))
        stage = str(e.get("stage"))
        if at is None:
            continue
        if e.get("status") == "running":
            started.setdefault(stage, at)
        elif e.get("status") in ("done", "cached"):
            finished[stage] = at
    stages = []
    for stage in [*STAGE_ORDER, "recut"]:
        mine = [c for c in calls if c.get("stage") == stage]
        if stage == "recut" and not mine:
            continue
        seconds = None
        if stage in started and stage in finished:
            seconds = round((finished[stage] - started[stage]).total_seconds(), 1)
        stages.append(
            {
                "stage": stage,
                "status": job.stages.get(stage, "done" if mine else "waiting"),
                "seconds": seconds,
                "calls": len(mine),
                "models": sorted({str(c.get("model")) for c in mine if c.get("model")}),
                "cost_usd": str(
                    sum((Decimal(str(c.get("cost_usd") or 0)) for c in mine), Decimal(0))
                ),
                "input_tokens": sum(int(c.get("input_tokens") or 0) for c in mine),
                "output_tokens": sum(int(c.get("output_tokens") or 0) for c in mine),
                "errors": sum(1 for c in mine if c.get("error")),
            }
        )
    all_times = [*started.values(), *finished.values()]
    total_s = round((max(all_times) - min(all_times)).total_seconds(), 1) if all_times else None

    transcript: list[dict[str, Any]] = []
    tpath = work / "work" / "stages" / "transcribe.json"
    if tpath.exists():
        try:
            doc = json.loads(tpath.read_text(encoding="utf-8")).get("output", {})
            transcript = [
                {"start_s": c.get("start_s"), "end_s": c.get("end_s"), "text": c.get("text", "")}
                for c in doc.get("chunks", [])
            ]
        except (json.JSONDecodeError, AttributeError):
            transcript = []

    products = db.scalars(
        select(Product).where(Product.job_id == job.id).order_by(Product.idx)
    ).all()
    upload = db.get(Upload, job.upload_id)
    frames = cut_frames(work)
    return {
        "id": str(job.id),
        "status": job.status,
        "created_at": iso_utc(job.created_at),
        "duration_s": round(upload.duration_s, 1) if upload else None,
        "total_seconds": total_s,
        "cost_usd": job.cost_usd,
        "stages": stages,
        "transcript": transcript,
        "items": [
            {
                "idx": p.idx,
                "title_en": p.title_en,
                "title_hi": p.title_hi,
                "price_inr": p.price_inr,
                "source": p.price_source,
                "confidence": round(p.confidence, 2),
                "removed": p.removed,
                "first_seen_s": p.first_seen_s,
                "last_seen_s": p.last_seen_s,
                "evidence": p.evidence,
                "image_url": f"/api/v1/jobs/{job.id}/images/{p.idx}" if p.image_key else None,
                "frame_url": f"/api/v1/jobs/{job.id}/frames/{p.idx}" if p.idx in frames else None,
            }
            for p in products
        ],
    }


@router.get("/jobs/{job_id}/frames/{idx}", tags=["insights"])
def job_frame(
    job_id: uuid.UUID, idx: int, request: Request, seller: SellerDep, db: SessionDep
) -> FileResponse:
    job = _job(db, seller.workspace, job_id)
    path = cut_frames(_storage(request).path(job.work_key)).get(idx)
    if path is None:
        raise AppError("not_found", "Frame not found.", status=404)
    return FileResponse(
        path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"}
    )
