"""Problem Details (RFC 9457) error responses with stable machine-readable codes."""

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from shelf.core.logging import get_logger
from shelf.core.request_id import current_request_id

PROBLEM_JSON = "application/problem+json"
log = get_logger(__name__)


class AppError(Exception):
    """An error we expect and can explain to the caller."""

    def __init__(
        self,
        code: str,
        title: str,
        status: int = 400,
        detail: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(title)
        self.code = code
        self.title = title
        self.status = status
        self.detail = detail
        self.extra = extra or {}


def problem(
    status: int, code: str, title: str, detail: str | None = None, **extra: Any
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://shelf-to-shop.dev/errors/{code}",
        "title": title,
        "status": status,
        "code": code,
        "request_id": current_request_id(),
    }
    if detail:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)


async def _app_error(_request: Request, exc: Exception) -> JSONResponse:
    exc = cast(AppError, exc)
    return problem(exc.status, exc.code, exc.title, exc.detail, **exc.extra)


async def _http_error(_request: Request, exc: Exception) -> JSONResponse:
    exc = cast(StarletteHTTPException, exc)
    code = {404: "not_found", 405: "method_not_allowed", 401: "unauthorized", 403: "forbidden"}
    return problem(exc.status_code, code.get(exc.status_code, "http_error"), str(exc.detail))


async def _validation_error(_request: Request, exc: Exception) -> JSONResponse:
    exc = cast(RequestValidationError, exc)
    # Report where and why, never the submitted values (they may hold personal data).
    errors = [
        {
            "loc": [str(p) for p in err.get("loc", ())],
            "msg": err.get("msg", ""),
            "type": err.get("type"),
        }
        for err in exc.errors()
    ]
    return problem(422, "validation_failed", "Some fields are missing or invalid.", errors=errors)


async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled_error", error_type=type(exc).__name__, exc_info=exc)
    return problem(
        500,
        "internal_error",
        "Something went wrong on our side.",
        "Try again in a minute. If it keeps happening, share the request id with support.",
    )


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled)
