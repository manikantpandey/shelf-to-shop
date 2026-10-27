"""Public shop pages' data: only what the seller approved and published. No sign-in."""

from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from engine.export.whatsapp import order_link
from engine.prices.inr import format_inr
from shelf.api.deps import SessionDep
from shelf.api.v1.insights import shop_today
from shelf.api.v1.shop import profile_out
from shelf.core.errors import AppError
from shelf.db.models import Catalog, Order, Section, ShopCounter, Workspace
from shelf.storage import LocalStorage

router = APIRouter(prefix="/public", tags=["public"])
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$")
_FILE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}\.jpg$")


def _shop(db: Session, slug: str) -> Workspace | None:
    """A real seller's shop; the sample shop that demo sign-ins copy is never public."""
    if not _SLUG.match(slug):
        return None
    return db.scalar(
        select(Workspace).where(Workspace.slug == slug, Workspace.is_template.is_(False))
    )


def _latest(db: Session, ws: Workspace) -> Catalog | None:
    return db.scalar(
        select(Catalog)
        .where(Catalog.workspace_id == ws.id)
        .order_by(Catalog.version.desc())
        .limit(1)
    )


def _count(db: Session, ws: Workspace, kind: str, item: str) -> None:
    """+1 on today's counter for this shop (and item, for order taps)."""
    key = (ShopCounter.workspace_id == ws.id, ShopCounter.day == shop_today(),
           ShopCounter.kind == kind, ShopCounter.item_id == item)  # fmt: skip
    row = db.scalar(select(ShopCounter).where(*key))
    if row is None:
        try:
            with db.begin_nested():
                db.add(ShopCounter(workspace_id=ws.id, day=shop_today(), kind=kind,
                                   item_id=item, count=1))  # fmt: skip
            return
        except IntegrityError:
            row = db.scalar(select(ShopCounter).where(*key))
    if row is not None:
        row.count += 1


@router.get("/shops/{slug}")
def shop(slug: str, request: Request, db: SessionDep) -> dict[str, Any]:
    ws = _shop(db, slug)
    latest = _latest(db, ws) if ws is not None else None
    if ws is None or latest is None:
        raise AppError("not_found", "This shop has not published a catalog yet.", status=404)
    # Profile and section names are read live, so the seller's edits show at once.
    used = {p.get("section") for p in latest.snapshot.get("products", [])}
    sections = db.scalars(
        select(Section).where(Section.workspace_id == ws.id).order_by(Section.position)
    ).all()
    return {
        "version": latest.version,
        **latest.snapshot,
        "profile": profile_out(ws, request.app.state.settings.api_url),
        "sections": [
            {"id": str(s.id), "name_en": s.name_en, "name_hi": s.name_hi}
            for s in sections
            if str(s.id) in used
        ],
    }


@router.get("/media/{slug}/v{version}/{file}")
def media(slug: str, version: int, file: str, request: Request, db: SessionDep) -> FileResponse:
    ws = _shop(db, slug)
    if not _FILE.match(file) or version < 1:
        raise AppError("not_found", "Photo not found.", status=404)
    published = ws is not None and db.scalar(
        select(Catalog.id).where(Catalog.workspace_id == ws.id, Catalog.version == version)
    )
    if not published:
        raise AppError("not_found", "Photo not found.", status=404)
    storage: LocalStorage = request.app.state.storage
    path = storage.path(f"public/{slug}/v{version}/images/{file}")
    if not path.exists():
        raise AppError("not_found", "Photo not found.", status=404)
    return FileResponse(
        path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400, immutable"}
    )


class ShopEvent(BaseModel):
    kind: Literal["view", "order"]
    item: str | None = Field(default=None, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")


@router.post("/shops/{slug}/events", status_code=204)
def count_event(slug: str, body: ShopEvent, db: SessionDep) -> Response:
    """Add one to today's page views or order taps. Only totals are kept: no visitor data."""
    ws = _shop(db, slug)
    latest = _latest(db, ws) if ws is not None else None
    if ws is None or latest is None:
        raise AppError("not_found", "This shop does not exist.", status=404)
    item = ""
    if body.kind == "order":
        ids = {p.get("id") for p in latest.snapshot.get("products", [])}
        if body.item not in ids:
            raise AppError("not_found", "That item is not in this shop.", status=404)
        item = body.item or ""
    _count(db, ws, body.kind, item)
    return Response(status_code=204)


@router.get("/shops/{slug}/logo")
def logo(slug: str, request: Request, db: SessionDep) -> FileResponse:
    ws = _shop(db, slug)
    if ws is None or not ws.logo_key or _latest(db, ws) is None:
        raise AppError("not_found", "Photo not found.", status=404)
    storage: LocalStorage = request.app.state.storage
    path = storage.path(ws.logo_key)
    if not path.exists():
        raise AppError("not_found", "Photo not found.", status=404)
    return FileResponse(
        path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"}
    )


class BasketLine(BaseModel):
    id: str = Field(max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    qty: int = Field(ge=1, le=99)


class Basket(BaseModel):
    items: list[BasketLine] = Field(min_length=1, max_length=30)
    name: str | None = Field(default=None, max_length=60)
    note: str | None = Field(default=None, max_length=200)
    lang: Literal["en", "hi"] = "en"


ORDER_TEXT = {
    "en": {
        "head": "Order #{number} for {shop}",
        "total": "Total: {total}",
        "name": "Name: {name}",
        "note": "Note: {note}",
        "shop": "Shop page: {url}",
    },
    "hi": {
        "head": "{shop} के लिए ऑर्डर #{number}",
        "total": "कुल: {total}",
        "name": "नाम: {name}",
        "note": "नोट: {note}",
        "shop": "दुकान का पेज: {url}",
    },
}


def order_text(
    shop: str, number: int, lines: list[dict[str, Any]], total_inr: int, url: str,
    name: str | None, note: str | None, lang: str,
) -> str:  # fmt: skip
    words = ORDER_TEXT.get(lang, ORDER_TEXT["en"])
    out = [words["head"].format(number=number, shop=shop)]
    for line in lines:
        cost = format_inr(line["price_inr"] * line["qty"] * 100)
        out.append(f"{line['qty']} x {line['title']} = {cost}")
    out.append(words["total"].format(total=format_inr(total_inr * 100)))
    if name:
        out.append(words["name"].format(name=name))
    if note:
        out.append(words["note"].format(note=note))
    out.append(words["shop"].format(url=url))
    return "\n".join(out)


def _clean(text: str | None) -> str | None:
    """One line of plain text: no links or control characters reach the seller's WhatsApp."""
    if not text:
        return None
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"(?i)\b(?:https?://|www\.)\S+", "", text)
    return " ".join(text.split())[:200] or None


@router.post("/shops/{slug}/orders", status_code=201)
def place_order(slug: str, body: Basket, request: Request, db: SessionDep) -> dict[str, Any]:
    """A customer's basket: priced from the published shop (never from the browser), numbered,
    saved to the seller's order book, and turned into one WhatsApp message."""
    ws = _shop(db, slug)
    latest = _latest(db, ws) if ws is not None else None
    if ws is None or latest is None or not ws.whatsapp:
        raise AppError("not_found", "This shop does not exist.", status=404)
    products = {p["id"]: p for p in latest.snapshot.get("products", [])}
    lang = body.lang
    qty: dict[str, int] = {}
    for wanted in body.items:
        if wanted.id not in products:
            raise AppError(
                "item_gone", "An item in your basket is no longer in the shop.", status=409
            )
        if products[wanted.id].get("sold_out"):
            raise AppError(
                "sold_out",
                "An item in your basket is sold out. Remove it and send again.",
                status=409,
            )
        qty[wanted.id] = min(99, qty.get(wanted.id, 0) + wanted.qty)
    lines: list[dict[str, Any]] = []
    for item_id, count in qty.items():
        p = products[item_id]
        lines.append({
            "id": item_id,
            "title": p["title_hi"] if lang == "hi" else p["title_en"],
            "qty": count,
            "price_inr": int(p["price_paise"]) // 100,
        })  # fmt: skip
    total = sum(line["price_inr"] * line["qty"] for line in lines)
    db.execute(
        update(Workspace).where(Workspace.id == ws.id).values(order_seq=Workspace.order_seq + 1)
    )
    # Unique (shop, number) stops two concurrent orders from sharing a number.
    number = int(db.scalar(select(Workspace.order_seq).where(Workspace.id == ws.id)) or 1)
    name, note = _clean(body.name), _clean(body.note)
    db.add(
        Order(workspace_id=ws.id, number=number, customer_name=name, note=note, items=lines,
              total_inr=total, lang=lang)
    )  # fmt: skip
    for line in lines:
        _count(db, ws, "order", line["id"])
    settings = request.app.state.settings
    url = f"{settings.public_base_url}/s/{ws.slug}"
    message = order_text(ws.name, number, lines, total, url, name, note, lang)
    return {
        "number": number,
        "total_inr": total,
        "total_display": format_inr(total * 100),
        "whatsapp_url": order_link(ws.whatsapp, message),
    }
