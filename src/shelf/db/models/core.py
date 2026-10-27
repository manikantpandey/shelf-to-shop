"""Core tables: who the seller is, their uploads, jobs, review state and published catalogs.

Every row that belongs to a seller carries `workspace_id`; queries always filter on it.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from shelf.db.base import Base, IdMixin, TimestampMixin


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str | None] = mapped_column(String(320), unique=True, default=None)
    display_name: Mapped[str] = mapped_column(String(120))


class Workspace(IdMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"

    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    whatsapp: Mapped[str | None] = mapped_column(String(20), default=None)  # digits, with country
    language: Mapped[str] = mapped_column(String(5), default="en")
    ai_mark: Mapped[bool] = mapped_column(default=True)
    raw_retention_days: Mapped[int] = mapped_column(default=7)
    consent_account_at: Mapped[datetime | None] = mapped_column(default=None)
    consent_recording_at: Mapped[datetime | None] = mapped_column(default=None)
    # The sample shop that demo sign-ins copy; nobody signs into it.
    is_template: Mapped[bool] = mapped_column(default=False)


class SessionRow(IdMixin, TimestampMixin, Base):
    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hmac: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)


class Upload(IdMixin, TimestampMixin, Base):
    __tablename__ = "uploads"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(300))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    container: Mapped[str] = mapped_column(String(16))
    duration_s: Mapped[float]
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)


class Job(IdMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_workspace_created", "workspace_id", "created_at"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    upload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"))
    # queued -> running -> needs_review -> published | failed
    status: Mapped[str] = mapped_column(String(20), default="queued")
    stages: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(40), default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    cost_usd: Mapped[str] = mapped_column(String(20), default="0")
    work_key: Mapped[str] = mapped_column(String(300))


class Product(IdMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("job_id", "idx"),)

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    idx: Mapped[int]
    title_en: Mapped[str] = mapped_column(String(200))
    title_hi: Mapped[str] = mapped_column(String(200))
    description_en: Mapped[str] = mapped_column(Text, default="")
    description_hi: Mapped[str] = mapped_column(Text, default="")
    price_inr: Mapped[int | None] = mapped_column(default=None)
    price_source: Mapped[str] = mapped_column(String(20), default="none")
    confidence: Mapped[float] = mapped_column(default=0.0)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    category: Mapped[str] = mapped_column(String(40), default="other")
    colour: Mapped[str] = mapped_column(String(60), default="")
    brand: Mapped[str | None] = mapped_column(String(100), default=None)
    material: Mapped[str | None] = mapped_column(String(60), default=None)
    pattern: Mapped[str | None] = mapped_column(String(60), default=None)
    image_key: Mapped[str | None] = mapped_column(String(300), default=None)
    ai_background: Mapped[bool] = mapped_column(default=False)
    # video (the pipeline's cut-out) | frame (seller picked another moment) | upload | openfoodfacts
    image_source: Mapped[str] = mapped_column(String(20), default="video")
    image_credit: Mapped[str | None] = mapped_column(String(200), default=None)
    image_credit_url: Mapped[str | None] = mapped_column(String(300), default=None)
    first_seen_s: Mapped[float | None] = mapped_column(default=None)
    last_seen_s: Mapped[float | None] = mapped_column(default=None)
    best_frame_s: Mapped[float | None] = mapped_column(default=None)
    sold_out: Mapped[bool] = mapped_column(default=False)
    removed: Mapped[bool] = mapped_column(default=False)


class FlagRow(IdMixin, TimestampMixin, Base):
    __tablename__ = "flags"

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    product_idx: Mapped[int | None] = mapped_column(default=None)
    kind: Mapped[str] = mapped_column(String(30))
    question_key: Mapped[str] = mapped_column(String(60))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    options: Mapped[list[int]] = mapped_column(JSON, default=list)
    candidates: Mapped[list[int]] = mapped_column(JSON, default=list)
    # open -> resolved | dismissed
    status: Mapped[str] = mapped_column(String(12), default="open")
    resolution: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


class Catalog(IdMixin, TimestampMixin, Base):
    __tablename__ = "catalogs"
    __table_args__ = (UniqueConstraint("workspace_id", "version"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    version: Mapped[int]
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    folder_key: Mapped[str] = mapped_column(String(300))
    approved_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))


class ShopCounter(IdMixin, Base):
    """Daily totals of shop page views and "Order on WhatsApp" taps; no visitor data is kept."""

    __tablename__ = "shop_counters"
    __table_args__ = (UniqueConstraint("workspace_id", "day", "kind", "item_id"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    day: Mapped[date]
    kind: Mapped[str] = mapped_column(String(10))  # view | order
    item_id: Mapped[str] = mapped_column(String(80), default="")  # "" for page views
    count: Mapped[int] = mapped_column(default=0)


class AuditEvent(IdMixin, TimestampMixin, Base):
    __tablename__ = "audit_events"

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    actor: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(60))
    target: Mapped[str | None] = mapped_column(String(120), default=None)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
