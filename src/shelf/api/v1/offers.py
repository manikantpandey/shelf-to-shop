"""Offers the seller runs: Diwali sale, festival offer, weekend sale, new stock, clearance.

Starting one lowers the chosen items' prices and republishes the shop; ending it puts them back.
The web app then lets the seller send a ready-made message from their own WhatsApp.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from shelf.api.deps import SessionDep, SettingsDep
from shelf.auth.sessions import SellerDep
from shelf.catalog.offers import (
    covered_items,
    end_if_due,
    end_offer,
    is_published,
    offer_out,
    start_offer,
)
from shelf.catalog.publish import active_offer
from shelf.core.clock import india_today
from shelf.core.errors import AppError
from shelf.core.ratelimit import OFFER_PER_SELLER, limiter
from shelf.db.models import Offer
from shelf.storage import LocalStorage

router = APIRouter(tags=["offers"])
PAST_SHOWN = 10

OfferKind = Literal["diwali", "festival", "weekend", "new_stock", "clearance", "custom"]
OfferScope = Literal["all", "section", "items"]


def _storage(request: Request) -> LocalStorage:
    storage: LocalStorage = request.app.state.storage
    return storage


def _one_line(value: str) -> str:
    return " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", value).split())


@router.get("/offers")
def list_offers(
    request: Request, seller: SellerDep, db: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    ws = seller.workspace
    end_if_due(db, settings, _storage(request), ws)
    active = active_offer(db, ws.id)
    past = db.scalars(
        select(Offer)
        .where(Offer.workspace_id == ws.id, Offer.ended_at.is_not(None))
        .order_by(Offer.created_at.desc(), Offer.id.desc())
        .limit(PAST_SHOWN)
    ).all()
    shop_url = f"{settings.public_base_url}/s/{ws.slug}" if is_published(db, ws.id) else None
    return {
        "active": offer_out(active) if active is not None else None,
        "past": [offer_out(o) for o in past],
        "shop_url": shop_url,
    }


class NewOffer(BaseModel):
    kind: OfferKind
    title_en: str = Field(min_length=1, max_length=80)
    title_hi: str | None = Field(default=None, max_length=80)
    # None: an announcement only, prices unchanged.
    percent_off: int | None = Field(default=None, ge=1, le=90)
    scope: OfferScope
    section_id: uuid.UUID | None = None
    item_ids: list[uuid.UUID] | None = Field(default=None, max_length=500)
    # Last day of the offer (India date, inclusive).
    ends_on: date

    @field_validator("title_en")
    @classmethod
    def _title_en(cls, value: str) -> str:
        value = _one_line(value)
        if not value:
            raise ValueError("Give the offer a name")
        return value

    @field_validator("title_hi")
    @classmethod
    def _title_hi(cls, value: str | None) -> str | None:
        return _one_line(value or "") or None


@router.post("/offers", status_code=201)
def start(
    body: NewOffer, request: Request, seller: SellerDep, db: SessionDep, settings: SettingsDep
) -> dict[str, Any]:
    """Start an offer: lower the prices it covers and republish the shop once."""
    ws = seller.workspace
    limiter(request).hit(OFFER_PER_SELLER, str(ws.id))
    if body.ends_on < india_today():
        raise AppError("ends_on_past", "That day has gone. Pick today or a later day.", status=422)
    if body.scope == "section" and body.section_id is None:
        raise AppError("pick_section", "Pick a section.", status=422)
    if body.scope == "items" and not body.item_ids:
        raise AppError("pick_items", "Pick at least one item.", status=422)
    section_id = body.section_id if body.scope == "section" else None
    item_ids = list(dict.fromkeys(body.item_ids or [])) if body.scope == "items" else []
    items = covered_items(db, ws, body.scope, section_id, item_ids)
    storage = _storage(request)
    # An offer past its last day that the hourly sweep has not reached yet must not block this.
    end_if_due(db, settings, storage, ws)
    offer = Offer(
        workspace_id=ws.id,
        kind=body.kind,
        title_en=body.title_en,
        title_hi=body.title_hi,
        percent_off=body.percent_off,
        scope=body.scope,
        section_id=section_id,
        item_ids=[str(i) for i in item_ids],
        ends_on=body.ends_on,
    )
    version = start_offer(db, settings, storage, ws, seller.user, offer, items)
    return {"offer": offer_out(offer), "shop_version": version}


@router.post("/offers/{offer_id}/end")
def end(
    offer_id: uuid.UUID,
    request: Request,
    seller: SellerDep,
    db: SessionDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    """End an offer now: prices go back and the shop is republished once."""
    limiter(request).hit(OFFER_PER_SELLER, str(seller.workspace.id))
    offer = db.scalar(
        select(Offer).where(Offer.id == offer_id, Offer.workspace_id == seller.workspace.id)
    )
    if offer is None:
        raise AppError("not_found", "That offer does not exist.", status=404)
    if offer.ended_at is not None:
        raise AppError("offer_ended", "This offer has already ended.", status=409)
    version = end_offer(db, settings, _storage(request), offer, seller.user)
    return {"offer": offer_out(offer), "shop_version": version}
