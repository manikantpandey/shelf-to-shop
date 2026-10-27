"""Cookie sessions: a random token in an HttpOnly cookie; only its HMAC is stored server-side.

Unsafe requests must also send the CSRF token (double submit: cookie plus X-CSRF-Token header).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from shelf.api.deps import SessionDep, SettingsDep
from shelf.config import Settings
from shelf.core.errors import AppError
from shelf.db.models import SessionRow, User, Workspace

SESSION_COOKIE = "sts_session"
CSRF_COOKIE = "sts_csrf"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def token_hmac(settings: Settings, token: str) -> str:
    key = settings.secret_key.get_secret_value().encode()
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def start_session(db: Session, settings: Settings, user: User, response: Response) -> SessionRow:
    token = secrets.token_urlsafe(32)
    row = SessionRow(
        user_id=user.id,
        token_hmac=token_hmac(settings, token),
        csrf_token=secrets.token_urlsafe(24),
        expires_at=datetime.now(UTC) + timedelta(hours=settings.session_hours),
    )
    db.add(row)
    db.flush()
    max_age = settings.session_hours * 3600
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        row.csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    return row


def end_session(db: Session, row: SessionRow, response: Response) -> None:
    row.revoked_at = datetime.now(UTC)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


@dataclass(frozen=True)
class Seller:
    """The signed-in user and their workspace; every query is scoped to `workspace.id`."""

    user: User
    workspace: Workspace
    session: SessionRow


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def current_seller(request: Request, db: SessionDep, settings: SettingsDep) -> Seller:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise AppError("signed_out", "Sign in to continue.", status=401)
    row = db.scalar(select(SessionRow).where(SessionRow.token_hmac == token_hmac(settings, token)))
    now = datetime.now(UTC)
    if row is None or row.revoked_at is not None or _aware(row.expires_at) < now:
        raise AppError("signed_out", "Your session has ended. Sign in again.", status=401)
    if request.method not in SAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not hmac.compare_digest(sent, row.csrf_token):
            raise AppError("csrf_failed", "Refresh the page and try again.", status=403)
    user = db.get(User, row.user_id)
    workspace = db.scalar(select(Workspace).where(Workspace.owner_id == row.user_id))
    if user is None or workspace is None:
        raise AppError("signed_out", "Sign in to continue.", status=401)
    return Seller(user=user, workspace=workspace, session=row)


SellerDep = Annotated[Seller, Depends(current_seller)]
