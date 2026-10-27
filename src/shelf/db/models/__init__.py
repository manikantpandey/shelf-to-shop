"""Import every model module here so Base.metadata knows all tables (Alembic relies on it)."""

from shelf.db.models.task import Task

__all__ = ["Task"]
