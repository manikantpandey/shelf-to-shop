"""All of a seller's items across videos: edit, mark sold out, remove, and replace weak photos.

A change to an item that is already on the shop republishes the shop straight away: the seller
made the change themselves, so it counts as their approval.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from engine.media.transcode import frame_at
from engine.pipeline.photos import PhotoRejectedError, recut, square_photo
from engine.prices.inr import format_inr
from engine.providers.errors import ProviderError
from engine.runlog import CallContext, JsonlRunLog
from engine.spend import InMemorySpendLedger, SpendCapExceededError
from shelf.api.deps import SessionDep, SettingsDep
from shelf.auth.sessions import Seller, SellerDep
from shelf.catalog.openfoodfacts import (
    CREDIT,
    OpenFoodFacts,
    SearchBusyError,
    thumb_size,
    valid_barcode,
)
from shelf.catalog.publish import item_id, publish_shop
from shelf.catalog.sections import category_for, ensure_sections
from shelf.config import Settings
from shelf.core.clock import iso_utc
from shelf.core.errors import AppError
from shelf.core.ids import uuid7
from shelf.db.models import AuditEvent, FlagRow, Job, Product, Section, Upload
from shelf.jobs.service import TeeRunLog, providers_for
from shelf.storage import LocalStorage

router = APIRouter(tags=["items"])
MOMENTS = 6
MAX_PHOTO_UPLOAD = 12 * 1024 * 1024
SHOWN_STATUSES = ("needs_review", "published")


def _storage(request: Request) -> LocalStorage:
    storage: LocalStorage = request.app.state.storage
    return storage


def _off(request: Request) -> OpenFoodFacts:
    client: OpenFoodFacts | None = getattr(request.app.state, "openfoodfacts", None)
    if client is None:
        raise AppError("not_available", "Pack photo search is switched off.", status=404)
    return client


def _item(db: Session, seller: Seller, product_id: uuid.UUID) -> tuple[Product, Job]:
    row = db.execute(
        select(Product, Job)
        .join(Job, Job.id == Product.job_id)
        .where(
            Product.id == product_id,
            Product.workspace_id == seller.workspace.id,
            Job.workspace_id == seller.workspace.id,
        )
    ).first()
    if row is None:
        raise AppError("not_found", "That item does not exist.", status=404)
    return row[0], row[1]


def item_out(p: Product, job: Job, slug: str) -> dict[str, Any]:
    version = int(p.updated_at.timestamp())
    on_shop = job.status == "published" and p.price_inr is not None and p.image_key is not None
    return {
        "id": str(p.id),
        "public_id": item_id(slug, p),
        "job_id": str(job.id),
        "from_video": job.kind == "video",
        "idx": p.idx,
        "title_en": p.title_en,
        "title_hi": p.title_hi,
        "price_inr": p.price_inr,
        "price_display": format_inr(p.price_inr * 100) if p.price_inr is not None else None,
        "mrp_inr": p.mrp_inr,
        "sold_out": p.sold_out,
        "hidden": p.hidden,
        "featured": p.featured,
        "section_id": str(p.section_id) if p.section_id else None,
        # On the shop page: published, priced, with a photo, and not hidden by the seller.
        "live": on_shop and not p.hidden,
        "published": job.status == "published",
        "category": p.category,
        "brand": p.brand,
        # The version query string makes the browser fetch a replaced photo.
        "image_url": f"/api/v1/jobs/{job.id}/images/{p.idx}?v={version}" if p.image_key else None,
        "image_source": p.image_source,
        "image_credit": p.image_credit,
        "ai_background": p.ai_background,
        "added_at": iso_utc(p.created_at),
    }


def _refresh_shop(
    db: Session, settings: Settings, storage: LocalStorage, seller: Seller, job: Job
) -> int | None:
    if job.status != "published":
        return None
    return publish_shop(db, settings, storage, seller.workspace, seller.user).version


@router.get("/items")
def list_items(seller: SellerDep, db: SessionDep) -> dict[str, Any]:
    ensure_sections(db, seller.workspace)
    rows = db.execute(
        select(Product, Job)
        .join(Job, Job.id == Product.job_id)
        .outerjoin(Section, Section.id == Product.section_id)
        .where(
            Product.workspace_id == seller.workspace.id,
            Product.removed.is_(False),
            Job.status.in_(SHOWN_STATUSES),
        )
        .order_by(Section.position, Product.featured.desc(), Job.created_at.desc(), Product.idx)
    ).all()
    return {"items": [item_out(p, j, seller.workspace.slug) for p, j in rows]}


def _section(db: Session, seller: Seller, section_id: uuid.UUID | None) -> Section | None:
    if section_id is None:
        return None
    found = db.scalar(
        select(Section).where(Section.id == section_id, Section.workspace_id == seller.workspace.id)
    )
    if found is None:
        raise AppError("not_found", "That section does not exist.", status=404)
    return found


class ItemPatch(BaseModel):
    title_en: str | None = Field(default=None, min_length=1, max_length=200)
    title_hi: str | None = Field(default=None, min_length=1, max_length=200)
    price_inr: int | None = Field(default=None, gt=0, le=10_000_000)
    # 0 clears the MRP.
    mrp_inr: int | None = Field(default=None, ge=0, le=10_000_000)
    sold_out: bool | None = None
    hidden: bool | None = None
    featured: bool | None = None
    section_id: uuid.UUID | None = None
    removed: bool | None = None


def _close_flags(db: Session, job: Job, p: Product) -> None:
    for f in db.scalars(
        select(FlagRow).where(
            FlagRow.job_id == job.id, FlagRow.product_idx == p.idx, FlagRow.status == "open"
        )
    ):
        f.status, f.resolution = "resolved", {"action": "removed"}


@router.patch("/items/{product_id}")
def edit_item(
    product_id: uuid.UUID,
    body: ItemPatch,
    request: Request,
    seller: SellerDep,
    db: SessionDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    p, job = _item(db, seller, product_id)
    if body.title_en is not None:
        p.title_en = body.title_en.strip()
    if body.title_hi is not None:
        p.title_hi = body.title_hi.strip()
    if body.price_inr is not None:
        p.price_inr, p.price_source, p.confidence = body.price_inr, "seller", 1.0
    if body.mrp_inr is not None:
        p.mrp_inr = body.mrp_inr or None
    if body.sold_out is not None:
        p.sold_out = body.sold_out
    if body.hidden is not None:
        p.hidden = body.hidden
    if body.featured is not None:
        p.featured = body.featured
    section = _section(db, seller, body.section_id)
    if section is not None:
        p.section_id = section.id
    if body.removed is not None:
        p.removed = body.removed
        if body.removed:
            _close_flags(db, job, p)
    db.flush()
    version = _refresh_shop(db, settings, _storage(request), seller, job)
    return {"item": item_out(p, job, seller.workspace.slug), "shop_version": version}


BulkAction = Literal[
    "sold_out", "in_stock", "hide", "show", "remove", "price_add", "price_percent", "section"
]


class Bulk(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    action: BulkAction
    # Rupees for price_add, percent for price_percent; either may be negative.
    value: int | None = Field(default=None, ge=-100_000, le=100_000)
    section_id: uuid.UUID | None = None


def _apply(db: Session, body: Bulk, p: Product, job: Job, target: Section | None) -> None:
    if body.action in ("sold_out", "in_stock"):
        p.sold_out = body.action == "sold_out"
    elif body.action in ("hide", "show"):
        p.hidden = body.action == "hide"
    elif body.action == "remove":
        p.removed = True
        _close_flags(db, job, p)
    elif body.action == "section" and target is not None:
        p.section_id = target.id
    elif p.price_inr is not None and body.value:
        if body.action == "price_add":
            new = p.price_inr + body.value
        else:
            new = round(p.price_inr * (100 + body.value) / 100)
        p.price_inr, p.price_source, p.confidence = max(1, new), "seller", 1.0


@router.post("/items/bulk")
def bulk_edit(
    body: Bulk, request: Request, seller: SellerDep, db: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    """Change many items at once (sold out, prices, section...), then republish the shop once."""
    rows = db.execute(
        select(Product, Job)
        .join(Job, Job.id == Product.job_id)
        .where(
            Product.id.in_(body.ids),
            Product.workspace_id == seller.workspace.id,
            Job.workspace_id == seller.workspace.id,
        )
    ).all()
    if len(rows) != len(set(body.ids)):
        raise AppError("not_found", "Some of those items do not exist.", status=404)
    if body.action in ("price_add", "price_percent") and not body.value:
        raise AppError("value_required", "Enter how much to change the price by.", status=422)
    target = _section(db, seller, body.section_id) if body.action == "section" else None
    if body.action == "section" and target is None:
        raise AppError("pick_section", "Pick a section.", status=422)
    for p, job in rows:
        _apply(db, body, p, job, target)
    db.add(
        AuditEvent(
            workspace_id=seller.workspace.id,
            actor=f"user:{seller.user.id}",
            action="items.bulk_edit",
            meta={"action": body.action, "items": len(rows)},
        )
    )
    db.flush()
    version = None
    if any(job.status == "published" for _, job in rows):
        shop = publish_shop(db, settings, _storage(request), seller.workspace, seller.user)
        version = shop.version
    return {
        "items": [item_out(p, job, seller.workspace.slug) for p, job in rows],
        "shop_version": version,
    }


def manual_job(db: Session, seller: Seller) -> Job:
    """The workspace's holder for items added by hand (no video); created the first time."""
    found = db.scalar(
        select(Job).where(Job.workspace_id == seller.workspace.id, Job.kind == "manual")
    )
    if found is not None:
        return found
    upload = Upload(
        workspace_id=seller.workspace.id,
        storage_key=f"ws/{seller.workspace.id}/uploads/manual.none",
        size_bytes=0,
        sha256="",
        container="none",
        duration_s=0.0,
        deleted_at=datetime.now(UTC),
    )
    db.add(upload)
    db.flush()
    job_id = uuid7()
    job = Job(
        id=job_id,
        workspace_id=seller.workspace.id,
        upload_id=upload.id,
        kind="manual",
        status="published",
        stages={},
        work_key=f"ws/{seller.workspace.id}/jobs/{job_id}",
    )
    db.add(job)
    db.flush()
    return job


class NewItem(BaseModel):
    title_en: str = Field(min_length=1, max_length=200)
    title_hi: str | None = Field(default=None, max_length=200)
    price_inr: int = Field(gt=0, le=10_000_000)
    mrp_inr: int | None = Field(default=None, gt=0, le=10_000_000)
    section_id: uuid.UUID | None = None


@router.post("/items", status_code=201)
def add_item(body: NewItem, seller: SellerDep, db: SessionDep) -> dict[str, Any]:
    """Add one item by hand. It goes on the shop once it has a photo."""
    section = _section(db, seller, body.section_id)
    job = manual_job(db, seller)
    idx = (db.scalar(select(func.max(Product.idx)).where(Product.job_id == job.id)) or 0) + 1
    title_en = body.title_en.strip()
    p = Product(
        job_id=job.id,
        workspace_id=seller.workspace.id,
        idx=idx,
        title_en=title_en,
        title_hi=(body.title_hi or "").strip() or title_en,
        price_inr=body.price_inr,
        price_source="seller",
        confidence=1.0,
        mrp_inr=body.mrp_inr,
        category=category_for(section),
        section_id=section.id if section else None,
        image_source="upload",
    )
    db.add(p)
    db.add(
        AuditEvent(
            workspace_id=seller.workspace.id,
            actor=f"user:{seller.user.id}",
            action="item.added",
        )
    )
    db.flush()
    return {"item": item_out(p, job, seller.workspace.slug), "shop_version": None}


def _photo_key(job: Job, p: Product, kind: str) -> str:
    return f"{job.work_key}/photos/{p.id.hex}-{kind}-{uuid.uuid4().hex[:8]}.jpg"


def _set_photo(
    db: Session,
    storage: LocalStorage,
    seller: Seller,
    p: Product,
    job: Job,
    data: bytes,
    source: str,
    credit: str | None = None,
    credit_url: str | None = None,
) -> None:
    key = _photo_key(job, p, source)
    dest = storage.path(key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    p.image_key, p.image_source, p.ai_background = key, source, False
    p.image_credit, p.image_credit_url = credit, credit_url
    db.add(
        AuditEvent(
            workspace_id=seller.workspace.id,
            actor=f"user:{seller.user.id}",
            action="item.photo_replaced",
            target=str(p.id),
            meta={"source": source},
        )
    )
    db.flush()


@router.post("/items/{product_id}/photo")
async def upload_photo(
    product_id: uuid.UUID,
    request: Request,
    seller: SellerDep,
    db: SessionDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    p, job = _item(db, seller, product_id)
    if int(request.headers.get("content-length") or 0) > MAX_PHOTO_UPLOAD:
        raise AppError("too_large", "The photo is over 12 MB. Pick a smaller one.", status=413)
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_PHOTO_UPLOAD:
            raise AppError("too_large", "The photo is over 12 MB. Pick a smaller one.", status=413)
    try:
        jpeg = await asyncio.to_thread(square_photo, bytes(data))
    except PhotoRejectedError as exc:
        raise AppError("not_a_photo", str(exc), status=422) from exc
    storage = _storage(request)
    _set_photo(db, storage, seller, p, job, jpeg, "upload")
    version = _refresh_shop(db, settings, storage, seller, job)
    return {"item": item_out(p, job, seller.workspace.slug), "shop_version": version}


# --- A better moment from the same video ----------------------------------------------------
def _moment_times(p: Product, duration_s: float) -> list[float]:
    if p.first_seen_s is not None and p.last_seen_s is not None:
        start, end = max(0.0, p.first_seen_s - 0.5), p.last_seen_s + 0.5
    else:
        start, end = 0.0, duration_s
    end = max(start, min(end, max(duration_s - 0.1, 0.0)))
    if end - start < 0.2:
        return [round(start, 2)]
    step = (end - start) / (MOMENTS - 1)
    return [round(start + i * step, 2) for i in range(MOMENTS)]


def _video(storage: LocalStorage, job: Job) -> Path:
    path = storage.path(f"{job.work_key}/work/ingest/video_720p.mp4")
    if not path.exists():
        raise AppError("video_gone", "The video for this item was deleted.", status=410)
    return path


def _moment_path(storage: LocalStorage, job: Job, p: Product, i: int, size: str) -> Path:
    return storage.path(f"{job.work_key}/moments/{p.id.hex}-{i}-{size}.jpg")


def _make_moment(video: Path, t: float, full: Path, thumb: Path) -> None:
    full.parent.mkdir(parents=True, exist_ok=True)
    if not full.exists():
        frame_at(video, t, full)
    if not thumb.exists():
        with Image.open(full) as im:
            small = im.convert("RGB")
            small.thumbnail((480, 480))
            small.save(thumb, "JPEG", quality=80)


@router.get("/items/{product_id}/moments")
async def list_moments(
    product_id: uuid.UUID, request: Request, seller: SellerDep, db: SessionDep
) -> dict[str, Any]:
    p, job = _item(db, seller, product_id)
    storage = _storage(request)
    video = _video(storage, job)
    upload = db.get(Upload, job.upload_id)
    times = _moment_times(p, upload.duration_s if upload else 60.0)
    for i, t in enumerate(times):
        await asyncio.to_thread(
            _make_moment,
            video,
            t,
            _moment_path(storage, job, p, i, "full"),
            _moment_path(storage, job, p, i, "small"),
        )
    return {
        "moments": [
            {"i": i, "t_s": t, "image_url": f"/api/v1/items/{p.id}/moments/{i}.jpg"}
            for i, t in enumerate(times)
        ]
    }


@router.get("/items/{product_id}/moments/{i}.jpg")
def moment_image(
    product_id: uuid.UUID, i: int, request: Request, seller: SellerDep, db: SessionDep
) -> FileResponse:
    p, job = _item(db, seller, product_id)
    path = _moment_path(_storage(request), job, p, i, "small")
    if not 0 <= i < MOMENTS or not path.exists():
        raise AppError("not_found", "That moment is not available.", status=404)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private"})


class MomentPick(BaseModel):
    i: int = Field(ge=0, lt=MOMENTS)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


@router.post("/items/{product_id}/photo/moment")
async def photo_from_moment(
    product_id: uuid.UUID,
    body: MomentPick,
    request: Request,
    seller: SellerDep,
    db: SessionDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    p, job = _item(db, seller, product_id)
    storage = _storage(request)
    frame = _moment_path(storage, job, p, body.i, "full")
    if not frame.exists():
        raise AppError("not_found", "Open the moments again and pick one.", status=404)
    work = storage.path(job.work_key)
    log = TeeRunLog(JsonlRunLog(work / "runlog.jsonl"))
    ctx = CallContext(
        job_id=str(job.id),
        workspace_id=str(seller.workspace.id),
        ledger=InMemorySpendLedger(settings.engine_config().caps),
        runlog=log,
    ).for_stage("recut")
    providers, client = providers_for(settings)
    try:
        jpeg = await recut(ctx, providers.segmenter, frame, body.x, body.y, p.title_en)
    except SpendCapExceededError as exc:
        raise AppError("spend_cap", "This would go over your spending limit.", status=402) from exc
    except ProviderError as exc:
        raise AppError(
            "model_unavailable", "Cutting out is busy. Try again in a minute.", status=503
        ) from exc
    finally:
        if client is not None:
            await client.aclose()
    if jpeg is None:
        raise AppError(
            "nothing_found",
            "Could not find an item where you tapped. Tap the middle of it.",
            status=422,
        )
    job.cost_usd = str(Decimal(job.cost_usd) + sum((e.cost_usd for e in log.entries), Decimal(0)))
    _set_photo(db, storage, seller, p, job, jpeg, "frame")
    version = _refresh_shop(db, settings, storage, seller, job)
    return {"item": item_out(p, job, seller.workspace.slug), "shop_version": version}


# --- Pack photos from Open Food Facts --------------------------------------------------------
@router.get("/photos/search")
async def search_pack_photos(
    request: Request, seller: SellerDep, q: str = "", barcode: str = ""
) -> dict[str, Any]:
    off = _off(request)
    try:
        if barcode:
            if not valid_barcode(barcode):
                raise AppError("bad_barcode", "A barcode has 8 to 14 digits.", status=422)
            one = await off.by_barcode(barcode)
            found = [one] if one else []
        else:
            found = await off.search(q)
    except SearchBusyError as exc:
        raise AppError(
            "busy", "Too many searches. Wait a minute and try again.", status=429
        ) from exc
    except httpx.HTTPError as exc:
        raise AppError(
            "search_down", "Photo search is not answering. Try again later.", status=503
        ) from exc
    return {
        "results": [
            {"code": r.code, "name": r.name, "brand": r.brand, "image_url": thumb_size(r.image_url)}
            for r in found
        ],
        "credit": CREDIT,
    }


class PackPick(BaseModel):
    code: str = Field(min_length=8, max_length=14)


@router.post("/items/{product_id}/photo/pack")
async def photo_from_pack(
    product_id: uuid.UUID,
    body: PackPick,
    request: Request,
    seller: SellerDep,
    db: SessionDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    p, job = _item(db, seller, product_id)
    off = _off(request)
    if not valid_barcode(body.code):
        raise AppError("bad_barcode", "A barcode has 8 to 14 digits.", status=422)
    try:
        # Look the product up again: the image URL always comes from Open Food Facts, never us.
        photo = await off.by_barcode(body.code)
        if photo is None:
            raise AppError("not_found", "That product has no photo. Pick another.", status=404)
        raw = await off.image(photo)
    except httpx.HTTPError as exc:
        raise AppError(
            "search_down", "Could not get that photo. Try again later.", status=503
        ) from exc
    try:
        jpeg = await asyncio.to_thread(square_photo, raw)
    except PhotoRejectedError as exc:
        raise AppError("bad_photo", "That photo cannot be used. Pick another.", status=422) from exc
    storage = _storage(request)
    _set_photo(db, storage, seller, p, job, jpeg, "openfoodfacts", CREDIT, photo.page_url)
    version = _refresh_shop(db, settings, storage, seller, job)
    return {"item": item_out(p, job, seller.workspace.slug), "shop_version": version}
