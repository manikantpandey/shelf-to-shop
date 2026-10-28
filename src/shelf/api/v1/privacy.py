"""The seller's own data: download all of it, or delete the shop and everything in it.

The export is a zip with one JSON file (shop, profile, sections, items, orders, videos) and the
current item photos. Deleting needs the shop's web name typed back, removes every row and file,
and ends the session; only an audit line without personal data remains.
"""

from __future__ import annotations

import json
import os
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.background import BackgroundTask

from shelf.api.deps import SessionDep, SettingsDep
from shelf.api.v1.shop import profile_out
from shelf.auth.sessions import CSRF_COOKIE, SESSION_COOKIE, SellerDep
from shelf.core.clock import iso_utc
from shelf.core.errors import AppError
from shelf.db.models import AuditEvent, Catalog, Job, Order, Product, Section, Upload, User
from shelf.storage import LocalStorage

router = APIRouter(tags=["privacy"])


def _storage(request: Request) -> LocalStorage:
    storage: LocalStorage = request.app.state.storage
    return storage


@router.get("/privacy/export")
def export_data(request: Request, seller: SellerDep, db: SessionDep) -> FileResponse:
    ws = seller.workspace
    storage = _storage(request)
    items = db.scalars(select(Product).where(Product.workspace_id == ws.id)).all()
    data: dict[str, Any] = {
        "exported_at": datetime.now(UTC).isoformat(),
        "shop": {"name": ws.name, "web_name": ws.slug, "whatsapp": ws.whatsapp,
                 "language": ws.language, "delete_videos_after_days": ws.raw_retention_days},
        "profile": profile_out(ws),
        "sections": [
            {"id": str(s.id), "name_en": s.name_en, "name_hi": s.name_hi, "position": s.position}
            for s in db.scalars(select(Section).where(Section.workspace_id == ws.id))
        ],
        "items": [
            {"id": str(p.id), "title_en": p.title_en, "title_hi": p.title_hi,
             "description_en": p.description_en, "description_hi": p.description_hi,
             "price_inr": p.price_inr, "mrp_inr": p.mrp_inr, "sold_out": p.sold_out,
             "hidden": p.hidden, "removed": p.removed, "category": p.category, "brand": p.brand,
             "section_id": str(p.section_id) if p.section_id else None,
             "photo": f"photos/{p.id}.jpg" if p.image_key else None,
             "photo_source": p.image_source, "price_evidence": p.evidence}
            for p in items
        ],
        "orders": [
            {"number": o.number, "created_at": iso_utc(o.created_at),
             "customer_name": o.customer_name, "note": o.note, "items": o.items,
             "total_inr": o.total_inr, "status": o.status, "paid": o.paid}
            for o in db.scalars(select(Order).where(Order.workspace_id == ws.id))
        ],
        "videos": [
            {"id": str(j.id), "created_at": iso_utc(j.created_at), "status": j.status,
             "model_cost_usd": j.cost_usd}
            for j in db.scalars(select(Job).where(Job.workspace_id == ws.id, Job.kind == "video"))
        ],
        "published_versions": len(
            db.scalars(select(Catalog.id).where(Catalog.workspace_id == ws.id)).all()
        ),
    }  # fmt: skip
    fd, name = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    path = Path(name)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("my-shop-data.json", json.dumps(data, ensure_ascii=False, indent=2))
        for p in items:
            if p.image_key:
                photo = storage.path(p.image_key)
                if photo.exists():
                    zf.write(photo, f"photos/{p.id}.jpg")
    db.add(AuditEvent(workspace_id=ws.id, actor=f"user:{seller.user.id}", action="privacy.export"))
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"{ws.slug}-data.zip",
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


class DeleteAll(BaseModel):
    # The shop's web name, typed back by the seller, so nothing is deleted by a stray tap.
    confirm: str = Field(min_length=1, max_length=80)


@router.post("/privacy/delete")
def delete_everything(
    body: DeleteAll,
    request: Request,
    response: Response,
    seller: SellerDep,
    db: SessionDep,
    settings: SettingsDep,
) -> dict[str, str]:
    ws, user = seller.workspace, seller.user
    if body.confirm.strip().lower() not in {ws.slug, ws.name.strip().lower()}:
        raise AppError("confirm_name", "Type your shop name exactly to delete it.", status=422)
    storage = _storage(request)
    for upload in db.scalars(select(Upload).where(Upload.workspace_id == ws.id)):
        storage.delete(upload.storage_key)
    storage.delete(f"ws/{ws.id}")
    storage.delete(f"public/{ws.slug}")
    workspace_id = ws.id
    # The user row owns the shop: deleting it removes the shop and every row that belongs to it.
    db.delete(db.get(User, user.id))
    db.flush()
    db.add(AuditEvent(workspace_id=workspace_id, actor="seller", action="privacy.shop_deleted"))
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"status": "deleted"}
