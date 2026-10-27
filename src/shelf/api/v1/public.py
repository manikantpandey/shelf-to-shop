"""Public shop pages' data: only what the seller approved and published. No sign-in."""

from __future__ import annotations

import re
from typing import Any, Literal

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shelf.api.deps import SessionDep
from shelf.api.v1.insights import shop_today
from shelf.core.errors import AppError
from shelf.db.models import Catalog, ShopCounter, Workspace
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


@router.get("/shops/{slug}")
def shop(slug: str, db: SessionDep) -> dict[str, Any]:
    ws = _shop(db, slug)
    latest = _latest(db, ws) if ws is not None else None
    if ws is None or latest is None:
        raise AppError("not_found", "This shop has not published a catalog yet.", status=404)
    return {"version": latest.version, **latest.snapshot}


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
    key = (ShopCounter.workspace_id == ws.id, ShopCounter.day == shop_today(),
           ShopCounter.kind == body.kind, ShopCounter.item_id == item)  # fmt: skip
    row = db.scalar(select(ShopCounter).where(*key))
    if row is None:
        try:
            with db.begin_nested():
                db.add(ShopCounter(workspace_id=ws.id, day=shop_today(), kind=body.kind,
                                   item_id=item, count=1))  # fmt: skip
            return Response(status_code=204)
        except IntegrityError:
            row = db.scalar(select(ShopCounter).where(*key))
    if row is not None:
        row.count += 1
    return Response(status_code=204)
