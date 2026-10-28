"""FastAPI application factory.

Run locally: uv run uvicorn --factory shelf.main:create_app --reload
"""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shelf.api.v1 import health, insights, items, privacy, public, seller, shop, uploads
from shelf.catalog.openfoodfacts import OpenFoodFacts
from shelf.config import Settings, get_settings
from shelf.core.errors import install_error_handlers
from shelf.core.logging import configure_logging, get_logger
from shelf.core.request_id import RequestIdMiddleware
from shelf.db.session import make_engine, make_session_factory
from shelf.jobs.service import PIPELINE_TASK, run_pipeline_job
from shelf.jobs.worker import Handler, Worker
from shelf.plugins import load_integration
from shelf.privacy.retention import Sweeper
from shelf.storage import LocalStorage
from shelf.version import VERSION

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    log = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        worker: Worker | None = None
        sweeper: Sweeper | None = None
        if settings.worker_inline:
            # Dev convenience: process jobs in this process. Production runs `shelf.jobs.worker`.
            worker = Worker(app.state.session_factory, pipeline_handlers(app))
            threading.Thread(target=worker.run_forever, name="inline-worker", daemon=True).start()
            sweeper = Sweeper(app.state.session_factory, app.state.storage)
            sweeper.start()
        yield
        if worker is not None:
            worker.stop()
        if sweeper is not None:
            sweeper.stop()
        if app.state.openfoodfacts is not None:
            await app.state.openfoodfacts.aclose()

    is_prod = settings.environment == "prod"
    app = FastAPI(
        title="Shelf-to-Shop API",
        version=VERSION,
        docs_url=None if is_prod else "/api/docs",
        redoc_url=None,
        openapi_url=None if is_prod else "/api/openapi.json",
        lifespan=lifespan,
    )
    engine = make_engine(settings.database_url)
    app.state.settings = settings
    app.state.db_engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.storage = LocalStorage(Path(settings.storage_dir))
    app.state.openfoodfacts = (
        OpenFoodFacts(settings.openfoodfacts_user_agent) if settings.openfoodfacts_enabled else None
    )

    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["content-type", "x-csrf-token", "x-request-id", "upload-offset"],
        max_age=600,
    )
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(uploads.router, prefix=API_PREFIX)
    app.include_router(seller.router, prefix=API_PREFIX)
    app.include_router(items.router, prefix=API_PREFIX)
    app.include_router(insights.router, prefix=API_PREFIX)
    app.include_router(shop.router, prefix=API_PREFIX)
    app.include_router(privacy.router, prefix=API_PREFIX)
    app.include_router(public.router, prefix=API_PREFIX)

    plugin = load_integration(app, settings)
    log.info("app_started", mode=settings.app_mode, environment=settings.environment, plugin=plugin)
    return app


def pipeline_handlers(app: FastAPI) -> dict[str, Handler]:
    settings: Settings = app.state.settings
    factory = app.state.session_factory
    storage: LocalStorage = app.state.storage
    return {
        PIPELINE_TASK: lambda task: run_pipeline_job(
            factory, settings, storage, task.payload["job_id"]
        )
    }
