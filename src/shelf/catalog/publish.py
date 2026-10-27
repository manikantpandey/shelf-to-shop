"""Publishing: only after the seller approves in the review screen, and only approved fields."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from engine.export.feed import FeedInvalidError
from engine.pipeline.publish import ShopInfo, publish
from engine.pipeline.schemas import DetectedProduct, Enriched, FinalImage, PriceDecision
from shelf.config import Settings
from shelf.core.errors import AppError
from shelf.db.models import AuditEvent, Catalog, Job, Product, User, Workspace
from shelf.jobs.service import open_flag_count
from shelf.storage import LocalStorage


def media_base(settings: Settings, slug: str, version: int) -> str:
    return f"{settings.public_base_url.rstrip('/')}/api/v1/public/media/{slug}/v{version}"


def publish_job(
    db: Session,
    settings: Settings,
    storage: LocalStorage,
    workspace: Workspace,
    user: User,
    job: Job,
) -> Catalog:
    if job.status not in ("needs_review", "published"):
        raise AppError("not_ready", "This catalog is not ready to publish yet.", status=409)
    if workspace.whatsapp is None:
        raise AppError(
            "whatsapp_missing", "Add your WhatsApp number in Settings first.", status=409
        )
    remaining = open_flag_count(db, job)
    if remaining:
        noun = "question" if remaining == 1 else "questions"
        raise AppError(
            "questions_open",
            f"Answer {remaining} {noun} first.",
            status=409,
            extra={"open_flags": remaining},
        )
    rows = db.scalars(
        select(Product)
        .where(Product.job_id == job.id, Product.removed.is_(False))
        .order_by(Product.idx)
    ).all()
    version = (
        db.scalar(select(func.max(Catalog.version)).where(Catalog.workspace_id == workspace.id))
        or 0
    ) + 1
    folder_key = f"public/{workspace.slug}/v{version}"
    shop = ShopInfo(
        name=workspace.name,
        slug=workspace.slug,
        whatsapp=workspace.whatsapp,
        public_base_url=settings.public_base_url,
        media_base_url=media_base(settings, workspace.slug, version),
    )
    products = [
        DetectedProduct(
            idx=r.idx,
            description=r.title_en,
            colour=r.colour,
            noun="item",
            first_seen_s=0,
            last_seen_s=0,
            best_frame_s=0,
        )
        for r in rows
    ]
    decisions = [
        PriceDecision(
            product_idx=r.idx, price_inr=r.price_inr, source="seller", confidence=r.confidence
        )
        for r in rows
    ]
    enriched = [
        Enriched(
            product_idx=r.idx,
            title_en=r.title_en,
            title_hi=r.title_hi,
            description_en=r.description_en,
            description_hi=r.description_hi,
            brand=r.brand,
            category=r.category,
            colour=r.colour,
            material=r.material,
            pattern=r.pattern,
        )
        for r in rows
    ]
    images = [
        FinalImage(product_idx=r.idx, path=storage.path(r.image_key), ai_background=r.ai_background)
        for r in rows
        if r.image_key
    ]
    try:
        result = publish(shop, products, decisions, enriched, images, storage.path(folder_key))
    except FeedInvalidError as exc:
        raise AppError(
            "feed_invalid",
            "Some items can't go into the Meta catalog: "
            + "; ".join(i.message for i in exc.issues[:3]),
            status=422,
        ) from exc
    if result.published == 0:
        raise AppError(
            "nothing_to_publish", "Add a price and photo to at least one item.", status=422
        )
    snapshot: dict[str, Any] = json.loads(result.catalog_json.read_text(encoding="utf-8"))
    for item in snapshot["products"]:
        item["image_url"] = f"{shop.media_base_url}/{item.pop('image')}"
    catalog = Catalog(
        workspace_id=workspace.id,
        job_id=job.id,
        version=version,
        snapshot=snapshot,
        folder_key=folder_key,
        approved_by=user.id,
    )
    db.add(catalog)
    job.status = "published"
    db.add(
        AuditEvent(
            workspace_id=workspace.id,
            actor=f"user:{user.id}",
            action="catalog.published",
            target=f"v{version}",
            meta={"items": result.published},
        )
    )
    db.flush()
    return catalog
