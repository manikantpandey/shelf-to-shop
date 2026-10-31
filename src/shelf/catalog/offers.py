"""Offers: a sale the seller runs (Diwali sale, weekend sale) with an optional percent off.

Starting one lowers the prices of the items it covers (the old price shows struck through as the
MRP) and republishes the shop. Ending it, by hand or after its last day, puts back every price the
seller has not changed in the meantime: the prices before and after are kept on the offer. The
server never messages customers; the seller shares the offer from their own WhatsApp.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from shelf.catalog.publish import SHOWN_STATUSES, active_offer, publish_shop
from shelf.catalog.sections import ensure_sections
from shelf.config import Settings
from shelf.core.clock import india_today, iso_utc
from shelf.core.errors import AppError
from shelf.core.logging import get_logger
from shelf.db.models import AuditEvent, Catalog, Job, Offer, Product, Section, User, Workspace
from shelf.storage import LocalStorage

log = get_logger(__name__)


def offer_out(o: Offer) -> dict[str, Any]:
    return {
        "id": str(o.id),
        "kind": o.kind,
        "title_en": o.title_en,
        "title_hi": o.title_hi,
        "percent_off": o.percent_off,
        "scope": o.scope,
        "section_id": str(o.section_id) if o.section_id else None,
        "item_ids": list(o.item_ids),
        "items_count": len(o.changes),
        "ends_on": o.ends_on.isoformat(),
        "started_at": iso_utc(o.created_at),
        "ended_at": iso_utc(o.ended_at) if o.ended_at else None,
        "active": o.ended_at is None,
    }


def offer_price(price_inr: int, percent_off: int) -> int:
    return max(1, round(price_inr * (100 - percent_off) / 100))


def is_published(db: Session, workspace_id: uuid.UUID) -> bool:
    found = db.scalar(select(Catalog.id).where(Catalog.workspace_id == workspace_id).limit(1))
    return found is not None


def covered_items(
    db: Session,
    workspace: Workspace,
    scope: str,
    section_id: uuid.UUID | None = None,
    item_ids: list[uuid.UUID] | None = None,
) -> list[Product]:
    """The items an offer covers: in scope, kept, priced, from videos the seller sees in Items.

    A section or item of another shop is "not found", like everywhere else.
    """
    query = (
        select(Product)
        .join(Job, Job.id == Product.job_id)
        .where(
            Product.workspace_id == workspace.id,
            Job.workspace_id == workspace.id,
            Product.removed.is_(False),
            Product.price_inr.is_not(None),
            Job.status.in_(SHOWN_STATUSES),
        )
    )
    if scope == "section":
        ensure_sections(db, workspace)
        found = db.scalar(
            select(Section.id).where(Section.id == section_id, Section.workspace_id == workspace.id)
        )
        if found is None:
            raise AppError("not_found", "That section does not exist.", status=404)
        query = query.where(Product.section_id == found)
    elif scope == "items":
        wanted = list(set(item_ids or []))
        mine = db.scalars(
            select(Product.id).where(Product.id.in_(wanted), Product.workspace_id == workspace.id)
        ).all()
        if len(mine) != len(wanted):
            raise AppError("not_found", "Some of those items do not exist.", status=404)
        query = query.where(Product.id.in_(wanted))
    return list(db.scalars(query).all())


def _republish(
    db: Session, settings: Settings, storage: LocalStorage, workspace: Workspace, user: User
) -> int | None:
    """A new shop version, if the shop is on the web. The seller started or ended the offer
    themselves (or set its last day), so it counts as their approval, as item edits do."""
    if not is_published(db, workspace.id):
        return None
    return publish_shop(db, settings, storage, workspace, user).version


def _running() -> AppError:
    return AppError(
        "offer_running", "An offer is already running. End it to start another.", status=409
    )


def _lower_prices(items: list[Product], percent_off: int) -> dict[str, dict[str, int | None]]:
    """Lower each price; the old price becomes the MRP unless the printed one is higher."""
    changes: dict[str, dict[str, int | None]] = {}
    for p in items:
        old = p.price_inr
        if old is None:
            continue
        new = offer_price(old, percent_off)
        if new == old:  # a 1-rupee item cannot go lower
            continue
        mrp = max(p.mrp_inr or 0, old)
        changes[str(p.id)] = {
            "price_inr": old,
            "mrp_inr": p.mrp_inr,
            "offer_price_inr": new,
            "offer_mrp_inr": mrp,
        }
        p.price_inr, p.mrp_inr = new, mrp
    return changes


def start_offer(
    db: Session,
    settings: Settings,
    storage: LocalStorage,
    workspace: Workspace,
    user: User,
    offer: Offer,
    items: list[Product],
) -> int | None:
    """Save the offer, lower the prices of `items` by its percent, and republish the shop.

    Returns the new shop version, or None when the shop is not published yet.
    """
    if active_offer(db, workspace.id) is not None:
        raise _running()
    db.add(offer)
    try:
        db.flush()
    except IntegrityError as exc:  # another start for this shop got there first
        raise _running() from exc
    changes = _lower_prices(items, offer.percent_off) if offer.percent_off else {}
    offer.changes = changes
    db.add(
        AuditEvent(
            workspace_id=workspace.id,
            actor=f"user:{user.id}",
            action="offer.started",
            target=str(offer.id),
            meta={
                "kind": offer.kind,
                "scope": offer.scope,
                "percent_off": offer.percent_off,
                "items": len(changes),
            },
        )
    )
    db.flush()
    return _republish(db, settings, storage, workspace, user)


def end_offer(
    db: Session, settings: Settings, storage: LocalStorage, offer: Offer, by: User | None = None
) -> int | None:
    """End a running offer: put back the prices it lowered, then republish the shop.

    `by` is the seller ending it by hand; None means its last day has passed. A price the seller
    changed during the offer is theirs and stays (and so does an MRP they changed).
    Returns the new shop version, or None when the shop is not published.
    """
    workspace = db.get(Workspace, offer.workspace_id)
    owner = by or (db.get(User, workspace.owner_id) if workspace is not None else None)
    if workspace is None or owner is None:
        raise AppError("not_found", "That offer does not exist.", status=404)
    now = datetime.now(UTC)
    # Only one caller can end it (the seller's tap and the hourly sweep may meet).
    result = db.execute(
        update(Offer)
        .where(Offer.id == offer.id, Offer.ended_at.is_(None))
        .values(ended_at=now, updated_at=now)
    )
    if int(getattr(result, "rowcount", 0) or 0) != 1:
        raise AppError("offer_ended", "This offer has already ended.", status=409)
    offer.ended_at = now
    restored = 0
    for product_id, change in offer.changes.items():
        p = db.scalar(
            select(Product).where(
                Product.id == uuid.UUID(product_id), Product.workspace_id == offer.workspace_id
            )
        )
        if p is None or p.price_inr != change["offer_price_inr"]:
            continue
        p.price_inr = change["price_inr"]
        if p.mrp_inr == change["offer_mrp_inr"]:
            p.mrp_inr = change["mrp_inr"]
        restored += 1
    db.add(
        AuditEvent(
            workspace_id=workspace.id,
            actor=f"user:{by.id}" if by is not None else "system",
            action="offer.ended",
            target=str(offer.id),
            meta={"items": restored, "automatic": by is None},
        )
    )
    db.flush()
    return _republish(db, settings, storage, workspace, owner)


def end_if_due(
    db: Session, settings: Settings, storage: LocalStorage, workspace: Workspace
) -> None:
    """End the shop's offer now if its last day has passed and the hourly sweep has not yet."""
    offer = active_offer(db, workspace.id)
    if offer is None or offer.ends_on >= india_today():
        return
    try:
        end_offer(db, settings, storage, offer)
    except AppError as exc:
        if exc.code != "offer_ended":  # the sweep ended it a moment ago: nothing left to do
            raise


def end_due_offers(
    factory: sessionmaker[Session],
    settings: Settings,
    storage: LocalStorage,
    today: date | None = None,
) -> int:
    """End every offer whose last day has passed, each shop in its own transaction, so one
    shop's failure does not hold up the others. Returns how many ended."""
    today = today or india_today()
    with factory() as db:
        due = db.scalars(
            select(Offer.id).where(Offer.ended_at.is_(None), Offer.ends_on < today)
        ).all()
    ended = 0
    for offer_id in due:
        try:
            with factory.begin() as db:
                offer = db.get(Offer, offer_id)
                if offer is None or offer.ended_at is not None:
                    continue
                end_offer(db, settings, storage, offer)
            ended += 1
        except AppError as exc:
            log.info("offer_end_skipped", offer_id=str(offer_id), code=exc.code)
        except Exception:
            log.exception("offer_end_failed", offer_id=str(offer_id))
    return ended
