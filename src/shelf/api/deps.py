"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from shelf.config import Settings
from shelf.db.session import session_scope


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_session(request: Request) -> Iterator[Session]:
    yield from session_scope(request.app.state.session_factory)


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
# scope="function": the session commits when the endpoint returns, before the response is sent.
# With the default request scope the commit ran after the client already had its answer, so a
# fast follow-up request (sign in, then /me) could miss rows the first one had just written.
SessionDep = Annotated[Session, Depends(get_session, scope="function")]
