"""FastAPI application factory.

Run locally: uv run uvicorn --factory shelf.main:create_app --reload
"""

from __future__ import annotations

from fastapi import FastAPI

from shelf.api.v1 import health
from shelf.config import Settings, get_settings
from shelf.core.errors import install_error_handlers
from shelf.core.logging import configure_logging, get_logger
from shelf.core.request_id import RequestIdMiddleware
from shelf.db.session import make_engine, make_session_factory
from shelf.plugins import load_integration
from shelf.version import VERSION

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    log = get_logger(__name__)

    is_prod = settings.environment == "prod"
    app = FastAPI(
        title="Shelf-to-Shop API",
        version=VERSION,
        docs_url=None if is_prod else "/api/docs",
        redoc_url=None,
        openapi_url=None if is_prod else "/api/openapi.json",
    )
    engine = make_engine(settings.database_url)
    app.state.settings = settings
    app.state.db_engine = engine
    app.state.session_factory = make_session_factory(engine)

    install_error_handlers(app)
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router, prefix=API_PREFIX)

    plugin = load_integration(app, settings)
    log.info("app_started", mode=settings.app_mode, environment=settings.environment, plugin=plugin)
    return app
