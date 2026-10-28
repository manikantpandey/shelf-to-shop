"""Seller API: demo sign-in, shop settings, consent, uploads, jobs, review and publishing.

Every query is scoped to the signed-in seller's workspace; another workspace's ids return 404.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session

from engine.export.whatsapp import InvalidWhatsAppNumberError, normalise_number
from engine.media.probe import (
    CLIP_S,
    LONG_UPLOAD_S,
    MediaRejectedError,
    MediaRules,
    probe,
    sniff_container,
)
from engine.prices.inr import format_inr
from shelf.api.deps import SessionDep, SettingsDep
from shelf.auth.sessions import SellerDep, end_session, start_session
from shelf.catalog.publish import publish_job
from shelf.core.clock import iso_utc
from shelf.core.errors import AppError
from shelf.core.ratelimit import SIGNIN_PER_IP, UPLOAD_PER_SELLER, client_ip, limiter
from shelf.db.models import AuditEvent, Catalog, FlagRow, Job, Product, Upload, User, Workspace
from shelf.demo import clone_template, find_template
from shelf.jobs.service import (
    create_job,
    open_flag_count,
    pending_task_exists,
    retry_job,
    settle_price_flags,
)
from shelf.storage import LocalStorage

router = APIRouter()
MAX_UPLOAD_BYTES = 200 * 1024**2


def _storage(request: Request) -> LocalStorage:
    storage: LocalStorage = request.app.state.storage
    return storage


def _audit(
    db: Session,
    seller_ws: uuid.UUID | None,
    actor: str,
    action: str,
    target: str | None = None,
    **meta: Any,
) -> None:
    db.add(AuditEvent(workspace_id=seller_ws, actor=actor, action=action, target=target, meta=meta))


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "shop"


def workspace_out(ws: Workspace) -> dict[str, Any]:
    return {
        "name": ws.name,
        "slug": ws.slug,
        "whatsapp": ws.whatsapp,
        "language": ws.language,
        "ai_mark": ws.ai_mark,
        "raw_retention_days": ws.raw_retention_days,
        "consent_account": ws.consent_account_at is not None,
        "consent_recording": ws.consent_recording_at is not None,
    }


# --- Sign-in ----------------------------------------------------------------------------
class DemoLogin(BaseModel):
    shop_name: str | None = Field(default=None, min_length=2, max_length=80)
    # Start from a private copy of the sample shop instead of an empty one.
    sample: bool = False
    # The language picked on the sign-in page becomes the shop's language.
    language: Literal["en", "hi"] | None = None


def _free_slug(db: Session, name: str) -> str:
    base = _slugify(name)
    slug = base
    while db.scalar(select(Workspace.id).where(Workspace.slug == slug)) is not None:
        slug = f"{base}-{secrets.token_hex(2)}"
    return slug


@router.post("/auth/demo", tags=["auth"])
def demo_login(
    body: DemoLogin, request: Request, response: Response, db: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    if not settings.demo_login_enabled:
        raise AppError("not_available", "Demo sign-in is switched off.", status=404)
    limiter(request).hit(SIGNIN_PER_IP, client_ip(request))
    template = find_template(db) if body.sample else None
    if body.sample and template is None:
        raise AppError("no_sample", "The sample shop is not set up yet.", status=404)
    if template is None and not (body.shop_name or "").strip():
        raise AppError("name_required", "Enter your shop name.", status=422)
    name = template.name if template is not None else (body.shop_name or "").strip()
    user = User(display_name=name)
    db.add(user)
    db.flush()
    if template is not None:
        ws = clone_template(db, settings, _storage(request), template, user, _free_slug(db, name))
    else:
        ws = Workspace(owner_id=user.id, name=name, slug=_free_slug(db, name))
        db.add(ws)
        db.flush()
    if body.language is not None:
        ws.language = body.language
    row = start_session(db, settings, user, response)
    _audit(db, ws.id, f"user:{user.id}", "auth.demo_login", sample=template is not None)
    # The CSRF token also travels in the body so a client on another origin (a future Android
    # shell) can send it; CORS keeps other sites from reading this response.
    return {"workspace": workspace_out(ws), "csrf_token": row.csrf_token}


@router.post("/auth/logout", tags=["auth"])
def logout(seller: SellerDep, response: Response, db: SessionDep) -> dict[str, str]:
    end_session(db, seller.session, response)
    _audit(db, seller.workspace.id, f"user:{seller.user.id}", "auth.logout")
    return {"status": "signed_out"}


@router.get("/me", tags=["auth"])
def me(seller: SellerDep, settings: SettingsDep) -> dict[str, Any]:
    return {
        "name": seller.user.display_name,
        "workspace": workspace_out(seller.workspace),
        "environment": settings.environment,
        "csrf_token": seller.session.csrf_token,
    }


# --- Workspace and consent ----------------------------------------------------------------
class WorkspacePatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    whatsapp: str | None = Field(default=None, max_length=24)
    language: Literal["en", "hi"] | None = None
    ai_mark: bool | None = None
    raw_retention_days: int | None = Field(default=None, ge=1, le=30)


@router.patch("/workspace", tags=["workspace"])
def update_workspace(body: WorkspacePatch, seller: SellerDep) -> dict[str, Any]:
    ws = seller.workspace
    if body.whatsapp is not None:
        try:
            ws.whatsapp = normalise_number(body.whatsapp)
        except InvalidWhatsAppNumberError as exc:
            raise AppError("whatsapp_invalid", str(exc).capitalize() + ".", status=422) from exc
    for field in ("name", "language", "ai_mark", "raw_retention_days"):
        value = getattr(body, field)
        if value is not None:
            setattr(ws, field, value)
    return {"workspace": workspace_out(ws)}


@router.post("/consents/{purpose}", tags=["workspace"])
def give_consent(
    purpose: Literal["account", "recording"], seller: SellerDep, db: SessionDep
) -> dict[str, Any]:
    now = datetime.now(UTC)
    if purpose == "account":
        seller.workspace.consent_account_at = now
    else:
        seller.workspace.consent_recording_at = now
    _audit(db, seller.workspace.id, f"user:{seller.user.id}", f"consent.{purpose}.given")
    return {"workspace": workspace_out(seller.workspace)}


@router.delete("/consents/{purpose}", tags=["workspace"])
def withdraw_consent(
    purpose: Literal["account", "recording"], seller: SellerDep, db: SessionDep
) -> dict[str, Any]:
    if purpose == "account":
        seller.workspace.consent_account_at = None
    seller.workspace.consent_recording_at = None
    _audit(db, seller.workspace.id, f"user:{seller.user.id}", f"consent.{purpose}.withdrawn")
    return {"workspace": workspace_out(seller.workspace)}


# --- Uploads ------------------------------------------------------------------------------
@router.post("/uploads", tags=["uploads"], status_code=201)
async def upload_video(request: Request, seller: SellerDep, db: SessionDep) -> dict[str, Any]:
    if seller.workspace.consent_recording_at is None:
        raise AppError("consent_required", "Agree to the recording notice first.", status=403)
    limiter(request).hit(UPLOAD_PER_SELLER, str(seller.workspace.id))
    declared = int(request.headers.get("content-length") or 0)
    if declared > MAX_UPLOAD_BYTES:
        raise AppError("too_large", "The video is over 200 MB. Record a shorter one.", status=413)
    storage = _storage(request)
    key = f"ws/{seller.workspace.id}/uploads/{uuid.uuid4().hex}.video"
    dest = storage.path(key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    digest = hashlib.sha256()
    with dest.open("wb") as fh:
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                fh.close()
                dest.unlink(missing_ok=True)
                raise AppError(
                    "too_large", "The video is over 200 MB. Record a shorter one.", status=413
                )
            digest.update(chunk)
            fh.write(chunk)
    row = Upload(
        workspace_id=seller.workspace.id,
        storage_key=key,
        size_bytes=size,
        sha256=digest.hexdigest(),
        container="",
        duration_s=0.0,
        received_bytes=size,
        expected_bytes=size,
    )
    db.add(row)
    db.flush()
    return check_upload(row, dest)


def upload_out(row: Upload) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "status": row.status,
        "offset": row.received_bytes,
        "size_bytes": row.expected_bytes or row.size_bytes,
        "duration_s": round(row.duration_s, 1),
        # Over this, the seller picks which part to use (POST /jobs with start_s).
        "max_clip_s": CLIP_S,
        "needs_clip": row.duration_s > MediaRules().max_duration_s,
    }


def check_upload(row: Upload, path: Path) -> dict[str, Any]:
    """The whole file is here: make sure it is a video we can use, then mark it ready."""
    with path.open("rb") as fh:
        container = sniff_container(fh.read(16))
    try:
        if container is None:
            raise MediaRejectedError(
                "not_a_video", "That file is not a video. Pick an MP4 or WebM."
            )
        # Longer videos are accepted; the seller then picks which minute to use.
        info = probe(path, MediaRules(max_duration_s=LONG_UPLOAD_S))
    except MediaRejectedError as exc:
        path.unlink(missing_ok=True)
        row.status = "rejected"
        # Keep the rejection although the request fails: the file is gone, so a phone that
        # retries must be told to start over rather than carry on.
        session = object_session(row)
        if session is not None:
            session.commit()
        raise AppError(exc.code, str(exc).capitalize() + ".", status=422) from exc
    if not row.sha256:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for block in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(block)
        row.sha256 = digest.hexdigest()
    row.status = "ready"
    row.container = info.container
    row.duration_s = info.duration_s
    row.size_bytes = row.received_bytes
    return upload_out(row)


# --- Jobs and review ----------------------------------------------------------------------
class NewJob(BaseModel):
    upload_id: uuid.UUID
    # For videos longer than one walk-past: where the part to use starts (it runs CLIP_S seconds).
    start_s: float | None = Field(default=None, ge=0)


def _job(db: Session, seller_ws: uuid.UUID, job_id: uuid.UUID) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id, Job.workspace_id == seller_ws))
    if job is None:
        raise AppError("not_found", "That catalog job does not exist.", status=404)
    return job


def job_out(job: Job, open_flags: int = 0) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "status": job.status,
        "stages": job.stages,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "open_flags": open_flags,
        "created_at": iso_utc(job.created_at),
    }


@router.post("/jobs", tags=["jobs"], status_code=201)
def new_job(body: NewJob, seller: SellerDep, db: SessionDep) -> dict[str, Any]:
    upload = db.scalar(
        select(Upload).where(
            Upload.id == body.upload_id, Upload.workspace_id == seller.workspace.id
        )
    )
    if upload is None:
        raise AppError("not_found", "That video was not found. Upload it again.", status=404)
    if upload.status != "ready":
        raise AppError("not_ready", "That video has not finished uploading.", status=409)
    clip: tuple[float, float] | None = None
    if upload.duration_s > MediaRules().max_duration_s:
        if body.start_s is None:
            raise AppError("pick_part", "This video is long. Pick the minute to use.", status=422)
        start = min(body.start_s, max(0.0, upload.duration_s - MediaRules().min_duration_s))
        clip = (round(start, 2), round(min(CLIP_S, upload.duration_s - start), 2))
    job = create_job(db, seller.workspace, upload, f"user:{seller.user.id}")
    if clip is not None:
        job.clip_start_s, job.clip_len_s = clip
    return job_out(job)


@router.get("/jobs", tags=["jobs"])
def list_jobs(seller: SellerDep, db: SessionDep) -> dict[str, Any]:
    jobs = db.scalars(
        select(Job)
        .where(Job.workspace_id == seller.workspace.id)
        .order_by(Job.created_at.desc())
        .limit(20)
    ).all()
    return {"jobs": [job_out(j) for j in jobs]}


@router.get("/jobs/{job_id}", tags=["jobs"])
def get_job(job_id: uuid.UUID, seller: SellerDep, db: SessionDep) -> dict[str, Any]:
    job = _job(db, seller.workspace.id, job_id)
    return job_out(job, open_flag_count(db, job))


@router.post("/jobs/{job_id}/retry", tags=["jobs"])
def retry(job_id: uuid.UUID, seller: SellerDep, db: SessionDep) -> dict[str, Any]:
    job = _job(db, seller.workspace.id, job_id)
    if job.status != "failed" or pending_task_exists(db, job):
        raise AppError("not_retryable", "This job is not waiting for a retry.", status=409)
    retry_job(db, job, f"user:{seller.user.id}")
    return job_out(job)


def product_out(p: Product, job_id: uuid.UUID) -> dict[str, Any]:
    version = int(p.updated_at.timestamp())
    return {
        "id": str(p.id),
        "idx": p.idx,
        "title_en": p.title_en,
        "title_hi": p.title_hi,
        "description_en": p.description_en,
        "description_hi": p.description_hi,
        "price_inr": p.price_inr,
        "price_display": format_inr(p.price_inr * 100) if p.price_inr is not None else None,
        "source": p.price_source,
        "confidence": p.confidence,
        "brand": p.brand,
        "category": p.category,
        "image_url": f"/api/v1/jobs/{job_id}/images/{p.idx}?v={version}" if p.image_key else None,
        "ai_background": p.ai_background,
        "removed": p.removed,
    }


def flag_out(f: FlagRow) -> dict[str, Any]:
    return {
        "id": str(f.id),
        "kind": f.kind,
        "product_idx": f.product_idx,
        "question_key": f.question_key,
        "params": f.params,
        "options": f.options,
        "candidates": f.candidates,
        "status": f.status,
    }


@router.get("/jobs/{job_id}/review", tags=["review"])
def review(job_id: uuid.UUID, seller: SellerDep, db: SessionDep) -> dict[str, Any]:
    job = _job(db, seller.workspace.id, job_id)
    products = db.scalars(
        select(Product).where(Product.job_id == job.id).order_by(Product.idx)
    ).all()
    flags = db.scalars(select(FlagRow).where(FlagRow.job_id == job.id)).all()
    return {
        "job": job_out(job, sum(1 for f in flags if f.status == "open")),
        "products": [product_out(p, job.id) for p in products],
        "flags": [flag_out(f) for f in flags],
    }


@router.get("/jobs/{job_id}/images/{idx}", tags=["review"])
def product_image(
    job_id: uuid.UUID, idx: int, request: Request, seller: SellerDep, db: SessionDep
) -> FileResponse:
    job = _job(db, seller.workspace.id, job_id)
    p = db.scalar(select(Product).where(Product.job_id == job.id, Product.idx == idx))
    if p is None or p.image_key is None:
        raise AppError("not_found", "No photo for this item.", status=404)
    return FileResponse(
        _storage(request).path(p.image_key),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=300"},
    )


def _product(db: Session, job: Job, idx: int) -> Product:
    p = db.scalar(select(Product).where(Product.job_id == job.id, Product.idx == idx))
    if p is None:
        raise AppError("not_found", "That item is not in this catalog.", status=404)
    return p


class ProductPatch(BaseModel):
    price_inr: int | None = Field(default=None, gt=0, le=10_000_000)
    title_en: str | None = Field(default=None, min_length=1, max_length=200)
    title_hi: str | None = Field(default=None, min_length=1, max_length=200)
    removed: bool | None = None


@router.patch("/jobs/{job_id}/products/{idx}", tags=["review"])
def edit_product(
    job_id: uuid.UUID, idx: int, body: ProductPatch, seller: SellerDep, db: SessionDep
) -> dict[str, Any]:
    job = _job(db, seller.workspace.id, job_id)
    p = _product(db, job, idx)
    if body.price_inr is not None:
        p.price_inr, p.price_source, p.confidence = body.price_inr, "seller", 1.0
        settle_price_flags(db, job, idx, {"action": "seller_price", "price_inr": body.price_inr})
    if body.title_en is not None:
        p.title_en = body.title_en.strip()
    if body.title_hi is not None:
        p.title_hi = body.title_hi.strip()
    if body.removed is not None:
        p.removed = body.removed
        if body.removed:
            for f in db.scalars(
                select(FlagRow).where(
                    FlagRow.job_id == job.id, FlagRow.product_idx == idx, FlagRow.status == "open"
                )
            ):
                f.status, f.resolution = "resolved", {"action": "removed"}
    return product_out(p, job.id)


class Resolve(BaseModel):
    action: Literal["set_price", "dismiss", "remove_item"]
    price_inr: int | None = Field(default=None, gt=0, le=10_000_000)
    product_idx: int | None = None


@router.post("/jobs/{job_id}/flags/{flag_id}/resolve", tags=["review"])
def resolve_flag(
    job_id: uuid.UUID, flag_id: uuid.UUID, body: Resolve, seller: SellerDep, db: SessionDep
) -> dict[str, Any]:
    job = _job(db, seller.workspace.id, job_id)
    flag = db.scalar(select(FlagRow).where(FlagRow.id == flag_id, FlagRow.job_id == job.id))
    if flag is None:
        raise AppError("not_found", "That question was already answered.", status=404)
    target = body.product_idx if body.product_idx is not None else flag.product_idx
    if body.action == "dismiss":
        flag.status, flag.resolution = "dismissed", {"action": "dismiss"}
    elif target is None or (flag.candidates and target not in flag.candidates):
        raise AppError("pick_item", "Pick which item this is for.", status=422)
    elif body.action == "remove_item":
        _product(db, job, target).removed = True
        flag.status, flag.resolution = "resolved", {"action": "remove_item", "product_idx": target}
    else:
        if body.price_inr is None:
            raise AppError("price_required", "Enter the price in rupees.", status=422)
        p = _product(db, job, target)
        p.price_inr, p.price_source, p.confidence = body.price_inr, "seller", 1.0
        flag.status = "resolved"
        flag.resolution = {
            "action": "set_price",
            "price_inr": body.price_inr,
            "product_idx": target,
        }
        settle_price_flags(db, job, target, flag.resolution)
    return flag_out(flag)


@router.post("/jobs/{job_id}/publish", tags=["review"])
def publish(
    job_id: uuid.UUID, request: Request, seller: SellerDep, db: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    job = _job(db, seller.workspace.id, job_id)
    catalog = publish_job(db, settings, _storage(request), seller.workspace, seller.user, job)
    return {
        "version": catalog.version,
        "url": f"{settings.public_base_url}/s/{seller.workspace.slug}",
    }


# --- The seller's published catalog ---------------------------------------------------------
def _latest(db: Session, workspace_id: uuid.UUID) -> Catalog | None:
    return db.scalar(
        select(Catalog)
        .where(Catalog.workspace_id == workspace_id)
        .order_by(Catalog.version.desc())
        .limit(1)
    )


@router.get("/catalog", tags=["catalog"])
def my_catalog(
    request: Request, seller: SellerDep, db: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    latest = _latest(db, seller.workspace.id)
    if latest is None:
        return {"published": False}
    report_path = _storage(request).path(latest.folder_key) / "feed_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    count = db.scalar(
        select(func.count()).select_from(Catalog).where(Catalog.workspace_id == seller.workspace.id)
    )
    return {
        "published": True,
        "version": latest.version,
        "versions": count,
        "published_at": iso_utc(latest.created_at),
        "items": len(latest.snapshot.get("products", [])),
        "url": f"{settings.public_base_url}/s/{seller.workspace.slug}",
        "feed_url": "/api/v1/catalog/feed.csv" if report.get("feed", True) else None,
        "feed_left_out": len(report.get("feed_left_out", [])),
        "feed_reasons": report.get("feed_reasons", []),
        "photos_url": "/api/v1/catalog/photos.zip",
    }


@router.get("/catalog/{name}", tags=["catalog"])
def download(
    name: Literal["feed.csv", "photos.zip"], request: Request, seller: SellerDep, db: SessionDep
) -> FileResponse:
    latest = _latest(db, seller.workspace.id)
    if latest is None:
        raise AppError("not_published", "Publish your catalog first.", status=404)
    folder = _storage(request).path(latest.folder_key)
    if name == "feed.csv":
        path, media = folder / "meta_catalog_feed.csv", "text/csv"
        if not path.exists():
            raise AppError("no_feed", "No item could go into the Meta catalog file.", status=404)
    else:
        path, media = folder / f"{seller.workspace.slug}_photos.zip", "application/zip"
    download_name = (
        f"{seller.workspace.slug}-{Path(name).stem}-v{latest.version}{Path(name).suffix}"
    )
    return FileResponse(path, media_type=media, filename=download_name)
