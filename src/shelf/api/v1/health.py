from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from shelf.api.deps import SessionDep, SettingsDep
from shelf.core.errors import AppError
from shelf.version import VERSION

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: SettingsDep) -> dict[str, str]:
    return {"status": "ok", "mode": settings.app_mode, "version": VERSION}


@router.get("/health/ready")
def ready(session: SessionDep) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:
        raise AppError("not_ready", "Database is not reachable.", status=503) from exc
    return {"status": "ready"}
