"""Running the shop: sections, the shop profile customers see, and the order book.

Profile and section names are read live by the public shop page, so saving them needs no republish.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from engine.pipeline.photos import PhotoRejectedError, square_photo
from engine.prices.inr import format_inr
from shelf.api.deps import SessionDep
from shelf.api.v1.insights import shop_today
from shelf.auth.sessions import Seller, SellerDep
from shelf.catalog.sections import ensure_sections
from shelf.core.clock import IST, iso_utc
from shelf.core.errors import AppError
from shelf.db.models import AuditEvent, Order, Product, Section, Workspace
from shelf.storage import LocalStorage

router = APIRouter()
MAX_LOGO = 8 * 1024 * 1024
_UPI = re.compile(r"^[A-Za-z0-9.\-_]{2,256}@[A-Za-z]{2,64}$")


def _storage(request: Request) -> LocalStorage:
    storage: LocalStorage = request.app.state.storage
    return storage


def _audit(db: Session, seller: Seller, action: str, **meta: Any) -> None:
    db.add(
        AuditEvent(
            workspace_id=seller.workspace.id,
            actor=f"user:{seller.user.id}",
            action=action,
            meta=meta,
        )
    )


# --- Shop profile ------------------------------------------------------------------------
def profile_out(ws: Workspace, api_url: str = "") -> dict[str, Any]:
    logo = None
    if ws.logo_key:
        version = int(ws.updated_at.timestamp())
        logo = f"{api_url}/api/v1/public/shops/{ws.slug}/logo?v={version}"
    return {
        "address": ws.address,
        "hours": ws.hours,
        "delivery": ws.delivery,
        "delivery_note": ws.delivery_note,
        "min_order_inr": ws.min_order_inr,
        "upi_id": ws.upi_id,
        "about": ws.about,
        "notice": ws.notice,
        "logo_url": logo,
    }


def _blank(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.split())
    return value or ""


class ProfilePatch(BaseModel):
    address: str | None = Field(default=None, max_length=200)
    hours: str | None = Field(default=None, max_length=80)
    delivery: Literal["pickup", "delivery", "both"] | None = None
    delivery_note: str | None = Field(default=None, max_length=120)
    # 0 clears the minimum.
    min_order_inr: int | None = Field(default=None, ge=0, le=1_000_000)
    upi_id: str | None = Field(default=None, max_length=100)
    about: str | None = Field(default=None, max_length=300)
    notice: str | None = Field(default=None, max_length=140)

    @field_validator("upi_id")
    @classmethod
    def _upi(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        if value and not _UPI.match(value):
            raise ValueError("A UPI ID looks like name@bank")
        return value


@router.get("/profile", tags=["shop"])
def get_profile(request: Request, seller: SellerDep) -> dict[str, Any]:
    return {"profile": profile_out(seller.workspace, request.app.state.settings.api_url)}


@router.patch("/profile", tags=["shop"])
def update_profile(
    body: ProfilePatch, request: Request, seller: SellerDep, db: SessionDep
) -> dict[str, Any]:
    ws = seller.workspace
    for field in ("address", "hours", "delivery_note", "upi_id", "about", "notice"):
        value = _blank(getattr(body, field))
        if value is not None:
            setattr(ws, field, value or None)
    if body.delivery is not None:
        ws.delivery = body.delivery
    if body.min_order_inr is not None:
        ws.min_order_inr = body.min_order_inr or None
    _audit(db, seller, "shop.profile_updated")
    db.flush()
    return {"profile": profile_out(ws, request.app.state.settings.api_url)}


@router.post("/profile/logo", tags=["shop"])
async def upload_logo(request: Request, seller: SellerDep, db: SessionDep) -> dict[str, Any]:
    if int(request.headers.get("content-length") or 0) > MAX_LOGO:
        raise AppError("too_large", "The photo is over 8 MB. Pick a smaller one.", status=413)
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_LOGO:
            raise AppError("too_large", "The photo is over 8 MB. Pick a smaller one.", status=413)
    try:
        jpeg = await asyncio.to_thread(square_photo, bytes(data))
    except PhotoRejectedError as exc:
        raise AppError("not_a_photo", str(exc), status=422) from exc
    ws = seller.workspace
    key = f"ws/{ws.id}/profile/logo-{uuid.uuid4().hex[:8]}.jpg"
    dest = _storage(request).path(key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(jpeg)
    ws.logo_key = key
    ws.updated_at = datetime.now(UTC)
    _audit(db, seller, "shop.logo_updated")
    db.flush()
    return {"profile": profile_out(ws, request.app.state.settings.api_url)}


# --- Sections -----------------------------------------------------------------------------
def section_out(s: Section, count: int) -> dict[str, Any]:
    return {"id": str(s.id), "name_en": s.name_en, "name_hi": s.name_hi, "items": count}


def _sections(db: Session, seller: Seller) -> list[dict[str, Any]]:
    sections = ensure_sections(db, seller.workspace)
    counts = dict(
        db.execute(
            select(Product.section_id, func.count())
            .where(Product.workspace_id == seller.workspace.id, Product.removed.is_(False))
            .group_by(Product.section_id)
        ).all()
    )
    ordered = sorted(sections, key=lambda s: (s.position, s.created_at))
    return [section_out(s, int(counts.get(s.id, 0))) for s in ordered]


def _section(db: Session, seller: Seller, section_id: uuid.UUID) -> Section:
    found = db.scalar(
        select(Section).where(Section.id == section_id, Section.workspace_id == seller.workspace.id)
    )
    if found is None:
        raise AppError("not_found", "That section does not exist.", status=404)
    return found


@router.get("/sections", tags=["shop"])
def list_sections(seller: SellerDep, db: SessionDep) -> dict[str, Any]:
    return {"sections": _sections(db, seller)}


class NewSection(BaseModel):
    name_en: str = Field(min_length=1, max_length=60)
    name_hi: str | None = Field(default=None, max_length=60)


@router.post("/sections", tags=["shop"], status_code=201)
def add_section(body: NewSection, seller: SellerDep, db: SessionDep) -> dict[str, Any]:
    last = db.scalar(
        select(func.max(Section.position)).where(Section.workspace_id == seller.workspace.id)
    )
    name = body.name_en.strip()
    db.add(
        Section(
            workspace_id=seller.workspace.id,
            name_en=name,
            name_hi=(body.name_hi or "").strip() or name,
            position=(last or 0) + 1,
        )
    )
    db.flush()
    return {"sections": _sections(db, seller)}


class SectionPatch(BaseModel):
    name_en: str | None = Field(default=None, min_length=1, max_length=60)
    name_hi: str | None = Field(default=None, min_length=1, max_length=60)


@router.patch("/sections/{section_id}", tags=["shop"])
def rename_section(
    section_id: uuid.UUID, body: SectionPatch, seller: SellerDep, db: SessionDep
) -> dict[str, Any]:
    section = _section(db, seller, section_id)
    if body.name_en is not None:
        section.name_en = body.name_en.strip()
    if body.name_hi is not None:
        section.name_hi = body.name_hi.strip()
    db.flush()
    return {"sections": _sections(db, seller)}


class SectionOrder(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


@router.post("/sections/order", tags=["shop"])
def reorder_sections(body: SectionOrder, seller: SellerDep, db: SessionDep) -> dict[str, Any]:
    mine = {s.id: s for s in ensure_sections(db, seller.workspace)}
    if set(body.ids) != set(mine):
        raise AppError("stale", "The sections changed. Reload and try again.", status=409)
    for position, sid in enumerate(body.ids, start=1):
        mine[sid].position = position
    db.flush()
    return {"sections": _sections(db, seller)}


@router.delete("/sections/{section_id}", tags=["shop"])
def delete_section(
    section_id: uuid.UUID, seller: SellerDep, db: SessionDep, move_to: uuid.UUID | None = None
) -> dict[str, Any]:
    """Delete a section; its items move to another section first, so nothing gets lost."""
    section = _section(db, seller, section_id)
    has_items = db.scalar(
        select(func.count()).select_from(Product).where(Product.section_id == section.id)
    )
    if has_items:
        if move_to is None or move_to == section.id:
            raise AppError("pick_section", "Pick where its items should go.", status=422)
        target = _section(db, seller, move_to)
        db.execute(
            update(Product).where(Product.section_id == section.id).values(section_id=target.id)
        )
    db.delete(section)
    db.flush()
    return {"sections": _sections(db, seller)}


# --- Orders -------------------------------------------------------------------------------
OrderStatus = Literal["new", "packed", "delivered", "cancelled"]


def order_out(o: Order) -> dict[str, Any]:
    return {
        "id": str(o.id),
        "number": o.number,
        "created_at": iso_utc(o.created_at),
        "customer_name": o.customer_name,
        "note": o.note,
        "items": o.items,
        "total_inr": o.total_inr,
        "total_display": format_inr(o.total_inr * 100),
        "status": o.status,
        "paid": o.paid,
    }


def _ist_day_start() -> datetime:
    start = datetime.combine(shop_today(), datetime.min.time(), tzinfo=IST)
    return start.astimezone(UTC).replace(tzinfo=None)


def order_summary(db: Session, workspace: Workspace) -> dict[str, Any]:
    counts = dict(
        db.execute(
            select(Order.status, func.count())
            .where(Order.workspace_id == workspace.id)
            .group_by(Order.status)
        ).all()
    )
    today = db.scalars(
        select(Order).where(
            Order.workspace_id == workspace.id,
            Order.created_at >= _ist_day_start(),
            Order.status != "cancelled",
        )
    ).all()
    return {
        "counts": {s: int(counts.get(s, 0)) for s in ("new", "packed", "delivered", "cancelled")},
        "today_orders": len(today),
        "today_total_inr": sum(o.total_inr for o in today),
        "today_paid_inr": sum(o.total_inr for o in today if o.paid),
    }


@router.get("/orders", tags=["orders"])
def list_orders(
    seller: SellerDep, db: SessionDep, status: OrderStatus | Literal["all"] = "all", days: int = 30
) -> dict[str, Any]:
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=max(1, min(days, 365)))
    query = (
        select(Order)
        .where(Order.workspace_id == seller.workspace.id, Order.created_at >= since)
        .order_by(Order.created_at.desc())
        .limit(200)
    )
    if status != "all":
        query = query.where(Order.status == status)
    return {
        "orders": [order_out(o) for o in db.scalars(query).all()],
        "summary": order_summary(db, seller.workspace),
    }


class OrderPatch(BaseModel):
    status: OrderStatus | None = None
    paid: bool | None = None


@router.patch("/orders/{order_id}", tags=["orders"])
def update_order(
    order_id: uuid.UUID, body: OrderPatch, seller: SellerDep, db: SessionDep
) -> dict[str, Any]:
    order = db.scalar(
        select(Order).where(Order.id == order_id, Order.workspace_id == seller.workspace.id)
    )
    if order is None:
        raise AppError("not_found", "That order does not exist.", status=404)
    if body.status is not None:
        order.status = body.status
    if body.paid is not None:
        order.paid = body.paid
    db.flush()
    return {"order": order_out(order), "summary": order_summary(db, seller.workspace)}
