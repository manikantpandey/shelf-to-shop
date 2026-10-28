"""Resumable video uploads: the phone sends the video in pieces and can carry on after a drop.

    POST  /uploads/sessions   {size}            -> {id, offset: 0, chunk_size}
    GET   /uploads/{id}                         -> {status, offset, ...}  (where to carry on from)
    PATCH /uploads/{id}       Upload-Offset: n  -> {status, offset, ...}  (one piece, raw bytes)

A piece must start exactly where the last one ended; a mismatch answers 409 with the right
offset, so a retried piece is never written twice. When the last byte arrives the file is checked
like a one-shot upload (content sniffed, ffprobe) and the upload becomes ready for a job.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shelf.api.deps import SessionDep
from shelf.api.v1.seller import MAX_UPLOAD_BYTES, check_upload, upload_out
from shelf.auth.sessions import Seller, SellerDep
from shelf.core.errors import AppError
from shelf.core.ratelimit import UPLOAD_PER_SELLER, limiter
from shelf.db.models import Upload
from shelf.storage import LocalStorage

router = APIRouter(tags=["uploads"])
CHUNK_BYTES = 4 * 1024 * 1024
MAX_CHUNK_BYTES = 8 * 1024 * 1024
# One writer per upload at a time (the deployment runs one API process).
_locks: dict[uuid.UUID, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock(upload_id: uuid.UUID) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(upload_id, threading.Lock())


def _storage(request: Request) -> LocalStorage:
    storage: LocalStorage = request.app.state.storage
    return storage


def _upload(db: Session, seller: Seller, upload_id: uuid.UUID) -> Upload:
    row = db.scalar(
        select(Upload).where(Upload.id == upload_id, Upload.workspace_id == seller.workspace.id)
    )
    if row is None or row.deleted_at is not None:
        raise AppError(
            "not_found", "That upload was not found. Start the upload again.", status=404
        )
    return row


class NewSession(BaseModel):
    size: int = Field(gt=0, le=MAX_UPLOAD_BYTES)


@router.post("/uploads/sessions", status_code=201)
def start_upload(
    body: NewSession, request: Request, seller: SellerDep, db: SessionDep
) -> dict[str, Any]:
    if seller.workspace.consent_recording_at is None:
        raise AppError("consent_required", "Agree to the recording notice first.", status=403)
    limiter(request).hit(UPLOAD_PER_SELLER, str(seller.workspace.id))
    key = f"ws/{seller.workspace.id}/uploads/{uuid.uuid4().hex}.video"
    path = _storage(request).path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    row = Upload(
        workspace_id=seller.workspace.id,
        storage_key=key,
        size_bytes=0,
        sha256="",
        container="",
        duration_s=0.0,
        status="receiving",
        received_bytes=0,
        expected_bytes=body.size,
    )
    db.add(row)
    db.flush()
    return {**upload_out(row), "chunk_size": CHUNK_BYTES}


@router.get("/uploads/{upload_id}")
def upload_status(upload_id: uuid.UUID, seller: SellerDep, db: SessionDep) -> dict[str, Any]:
    return upload_out(_upload(db, seller, upload_id))


@router.patch("/uploads/{upload_id}")
async def upload_piece(
    upload_id: uuid.UUID, request: Request, seller: SellerDep, db: SessionDep
) -> dict[str, Any]:
    row = _upload(db, seller, upload_id)
    if row.status != "receiving":
        return upload_out(row)  # already complete: a retried last piece is harmless
    try:
        offset = int(request.headers.get("upload-offset", ""))
    except ValueError as exc:
        raise AppError("bad_offset", "Missing Upload-Offset.", status=400) from exc
    if int(request.headers.get("content-length") or 0) > MAX_CHUNK_BYTES:
        raise AppError("too_large", "Send the video in smaller pieces.", status=413)
    data = bytearray()
    async for part in request.stream():
        data.extend(part)
        if len(data) > MAX_CHUNK_BYTES:
            raise AppError("too_large", "Send the video in smaller pieces.", status=413)
    expected = row.expected_bytes or 0
    with _lock(row.id):
        db.refresh(row)
        if offset != row.received_bytes:
            raise AppError(
                "offset_mismatch",
                "Carry on from the offset the server has.",
                status=409,
                extra={"offset": row.received_bytes},
            )
        if row.received_bytes + len(data) > expected:
            raise AppError("too_large", "More data than the upload said.", status=413)
        path = _storage(request).path(row.storage_key)
        with path.open("ab") as fh:
            fh.write(data)
        row.received_bytes += len(data)
        db.flush()
        if row.received_bytes < expected:
            return upload_out(row)
    return check_upload(row, path)
