"""Publishing: only after the seller approves in the review screen, and only approved fields."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from engine.pipeline.publish import ShopInfo, ShopItem, publish_items
from shelf.catalog.sections import ensure_sections
from shelf.config import Settings
from shelf.core.errors import AppError
from shelf.db.models import AuditEvent, Catalog, Job, Product, Section, User, Workspace
from shelf.jobs.service import open_flag_count
from shelf.storage import LocalStorage


def media_base(settings: Settings, slug: str, version: int) -> str:
    return f"{settings.api_url}/api/v1/public/media/{slug}/v{version}"


def item_id(slug: str, product: Product) -> str:
    """Retailer id for the feed and shop links: stable across republishes and videos."""
    return f"{slug}-{product.id.hex[-8:]}"


def live_products(
    db: Session, workspace: Workspace, extra_job: Job | None = None, *, with_hidden: bool = False
) -> list[Product]:
    """Items on the shop: every kept item from published videos (plus the one being published).

    In the seller's section order, pinned items first; then newest video first and, inside a
    video, the order the items appeared in.
    """
    ensure_sections(db, workspace)
    jobs = [Job.status == "published"]
    if extra_job is not None:
        jobs.append(Job.id == extra_job.id)
    query = (
        select(Product)
        .join(Job, Job.id == Product.job_id)
        .outerjoin(Section, Section.id == Product.section_id)
        .where(
            Job.workspace_id == workspace.id,
            Product.workspace_id == workspace.id,
            Product.removed.is_(False),
            or_(*jobs),
        )
        .order_by(Section.position, Product.featured.desc(), Job.created_at.desc(), Product.idx)
    )
    if not with_hidden:
        query = query.where(Product.hidden.is_(False))
    return list(db.scalars(query).all())


def publish_job(
    db: Session,
    settings: Settings,
    storage: LocalStorage,
    workspace: Workspace,
    user: User,
    job: Job,
) -> Catalog:
    """The seller approved one video's items: add them to the shop."""
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
    catalog = publish_shop(db, settings, storage, workspace, user, job=job)
    job.status = "published"
    return catalog


def publish_shop(
    db: Session,
    settings: Settings,
    storage: LocalStorage,
    workspace: Workspace,
    user: User,
    *,
    job: Job | None = None,
) -> Catalog:
    """Write a new version of the whole shop: page data, Meta feed and photo zip."""
    if workspace.whatsapp is None:
        raise AppError(
            "whatsapp_missing", "Add your WhatsApp number in Settings first.", status=409
        )
    rows = [r for r in live_products(db, workspace, job) if r.price_inr and r.image_key]
    if job is not None and not any(r.job_id == job.id for r in rows):
        raise AppError(
            "nothing_to_publish", "Add a price and photo to at least one item.", status=422
        )
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
    items = [
        ShopItem(
            id=item_id(workspace.slug, r),
            title_en=r.title_en,
            title_hi=r.title_hi,
            description_en=r.description_en,
            description_hi=r.description_hi,
            price_inr=r.price_inr or 0,
            image=storage.path(r.image_key or ""),
            ai_background=r.ai_background,
            sold_out=r.sold_out,
            category=r.category,
            colour=r.colour,
            brand=r.brand,
            material=r.material,
            pattern=r.pattern,
            image_credit=r.image_credit,
            image_credit_url=r.image_credit_url,
            mrp_inr=r.mrp_inr,
            section=str(r.section_id) if r.section_id else None,
            featured=r.featured,
        )
        for r in rows
    ]
    result = publish_items(shop, items, storage.path(folder_key))
    snapshot: dict[str, Any] = json.loads(result.catalog_json.read_text(encoding="utf-8"))
    for entry in snapshot["products"]:
        entry["image_url"] = f"{shop.media_base_url}/{entry.pop('image')}"
    feed_meta = {
        "feed": result.feed_csv is not None,
        "feed_left_out": sorted({i.item_id for i in result.feed_errors}),
        "feed_reasons": sorted({i.message for i in result.feed_errors})[:5],
    }
    # Private note for the seller's catalog screen (never part of the public snapshot).
    (storage.path(folder_key) / "feed_report.json").write_text(
        json.dumps(feed_meta), encoding="utf-8"
    )
    catalog = Catalog(
        workspace_id=workspace.id,
        job_id=job.id if job is not None else rows[0].job_id if rows else _any_job(db, workspace),
        version=version,
        snapshot=snapshot,
        folder_key=folder_key,
        approved_by=user.id,
    )
    db.add(catalog)
    db.add(
        AuditEvent(
            workspace_id=workspace.id,
            actor=f"user:{user.id}",
            action="catalog.published",
            target=f"v{version}",
            meta={"items": result.published, **feed_meta},
        )
    )
    db.flush()
    return catalog


def _any_job(db: Session, workspace: Workspace) -> Any:
    found = db.scalar(select(Job.id).where(Job.workspace_id == workspace.id).limit(1))
    if found is None:
        raise AppError("nothing_to_publish", "Record a video first.", status=422)
    return found
