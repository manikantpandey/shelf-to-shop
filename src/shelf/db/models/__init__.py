"""Import every model module here so Base.metadata knows all tables (Alembic relies on it)."""

from shelf.db.models.core import (
    AuditEvent,
    Catalog,
    FlagRow,
    Job,
    Order,
    Product,
    Section,
    SessionRow,
    ShopCounter,
    SpendDay,
    Upload,
    User,
    Workspace,
)
from shelf.db.models.task import Task

__all__ = [
    "AuditEvent",
    "Catalog",
    "FlagRow",
    "Job",
    "Order",
    "Product",
    "Section",
    "SessionRow",
    "ShopCounter",
    "SpendDay",
    "Task",
    "Upload",
    "User",
    "Workspace",
]
