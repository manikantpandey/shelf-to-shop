"""Alembic environment: DATABASE_URL from settings; batch mode keeps ALTERs SQLite-safe."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

import shelf.db.models  # noqa: F401  (registers every table on Base.metadata)
from shelf.config import get_settings
from shelf.db.base import Base
from shelf.db.session import make_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def _configure(connection: Connection | None = None) -> None:
    options = {
        "target_metadata": target_metadata,
        "render_as_batch": True,
        "compare_type": True,
    }
    if connection is None:
        context.configure(url=_url(), literal_binds=True, **options)
    else:
        context.configure(connection=connection, **options)


def run_migrations_offline() -> None:
    _configure()
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(_url())
    with engine.connect() as connection:
        _configure(connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
