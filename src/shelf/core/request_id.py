"""Request-id propagation and one structured access-log line per request (pure ASGI middleware)."""

from __future__ import annotations

import re
import time
import uuid
from contextvars import ContextVar

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from shelf.core.logging import get_logger

HEADER = "x-request-id"
_VALID = re.compile(r"^[A-Za-z0-9\-]{8,64}$")
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
log = get_logger("shelf.access")


def current_request_id() -> str | None:
    return _request_id.get()


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers", [])).get(HEADER.encode(), b"").decode("latin-1")
        request_id = incoming if _VALID.match(incoming) else uuid.uuid4().hex
        token = _request_id.set(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        status = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                headers.append((HEADER.encode(), request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            # Path only: query strings can carry signed tokens.
            log.info(
                "request",
                method=scope.get("method"),
                path=scope.get("path"),
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
            structlog.contextvars.unbind_contextvars("request_id")
            _request_id.reset(token)
