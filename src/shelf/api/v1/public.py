"""Public shop pages' data: only what the seller approved and published. No sign-in."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from sqlalchemy import select

from shelf.api.deps import SessionDep
from shelf.core.errors import AppError
from shelf.db.models import Catalog, Workspace
from shelf.storage import LocalStorage

router = APIRouter(prefix="/public", tags=["public"])
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$")
_FILE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}\.jpg$")


@router.get("/shops/{slug}")
def shop(slug: str, db: SessionDep) -> dict[str, Any]:
    if not _SLUG.match(slug):
        raise AppError("not_found", "This shop does not exist.", status=404)
    ws = db.scalar(select(Workspace).where(Workspace.slug == slug))
    latest = None
    if ws is not None:
        latest = db.scalar(
            select(Catalog)
            .where(Catalog.workspace_id == ws.id)
            .order_by(Catalog.version.desc())
            .limit(1)
        )
    if ws is None or latest is None:
        raise AppError("not_found", "This shop has not published a catalog yet.", status=404)
    return {"version": latest.version, **latest.snapshot}


@router.get("/media/{slug}/v{version}/{file}")
def media(slug: str, version: int, file: str, request: Request, db: SessionDep) -> FileResponse:
    if not _SLUG.match(slug) or not _FILE.match(file) or version < 1:
        raise AppError("not_found", "Photo not found.", status=404)
    ws = db.scalar(select(Workspace).where(Workspace.slug == slug))
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
