"""Privacy: videos deleted after the retention period, old order details cleared, export, delete."""

from __future__ import annotations

import io
import json
import shutil
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from shelf.config import Settings
from shelf.db.models import AuditEvent, Job, Order, Product, Upload, Workspace
from shelf.jobs.worker import Worker
from shelf.main import create_app, pipeline_handlers
from shelf.privacy.retention import sweep

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _shop(app: Any, c: TestClient, clip: bytes, name: str = "Privacy Shop") -> dict[str, str]:
    assert c.post("/api/v1/auth/demo", json={"shop_name": name}).status_code == 200
    h = {"x-csrf-token": c.cookies["sts_csrf"]}
    c.patch("/api/v1/workspace", json={"whatsapp": "98765 43210"}, headers=h)
    c.post("/api/v1/consents/recording", headers=h)
    upload = c.post("/api/v1/uploads", content=clip, headers={**h, "content-type": "video/mp4"})
    job = c.post("/api/v1/jobs", json={"upload_id": upload.json()["id"]}, headers=h).json()
    assert Worker(app.state.session_factory, pipeline_handlers(app), worker_id="t").run_once()
    for flag in c.get(f"/api/v1/jobs/{job['id']}/review").json()["flags"]:
        action = "remove_item" if flag["kind"] == "missing_price" else "dismiss"
        c.post(f"/api/v1/jobs/{job['id']}/flags/{flag['id']}/resolve", json={"action": action},
               headers=h)  # fmt: skip
    assert c.post(f"/api/v1/jobs/{job['id']}/publish", headers=h).status_code == 200
    return h


def _back(app: Any, model: Any, days: float) -> None:
    then = datetime.now(UTC) - timedelta(days=days)
    with app.state.session_factory.begin() as db:
        db.execute(update(model).values(created_at=then))


def test_videos_and_people_frames_go_after_the_retention_period(
    app_and_client: tuple[Any, TestClient], clip: bytes
) -> None:
    app, c = app_and_client
    _shop(app, c, clip)
    storage = app.state.storage
    with app.state.session_factory() as db:
        upload = db.scalar(select(Upload))
        job = db.scalar(select(Job))
        photos = [p.image_key for p in db.scalars(select(Product)) if p.image_key]
    work = storage.path(job.work_key)
    assert storage.path(upload.storage_key).exists() and (work / "work" / "ingest").exists()

    with app.state.session_factory.begin() as db:  # not old enough yet: nothing happens
        assert sweep(db, storage)["videos"] == 0
    _back(app, Upload, 8)
    with app.state.session_factory.begin() as db:
        assert sweep(db, storage)["videos"] == 1

    assert not storage.path(upload.storage_key).exists()
    assert not (work / "work" / "ingest").exists()
    assert not list((work / "work" / "segment").glob("frame_*.jpg"))
    assert all(storage.path(k).exists() for k in photos)  # item photos stay
    item = c.get("/api/v1/items").json()["items"][0]
    assert c.get(f"/api/v1/items/{item['id']}/moments").status_code == 410
    assert len(c.get("/api/v1/public/shops/privacy-shop").json()["products"]) == 2


def test_abandoned_uploads_and_old_order_details_are_cleared(
    app_and_client: tuple[Any, TestClient], clip: bytes
) -> None:
    app, c = app_and_client
    h = _shop(app, c, clip)
    session = c.post("/api/v1/uploads/sessions", json={"size": 5000}, headers=h).json()
    item = c.get("/api/v1/public/shops/privacy-shop").json()["products"][0]["id"]
    order = {"items": [{"id": item, "qty": 2}], "name": "Ravi", "note": "near the temple"}
    c.post("/api/v1/public/shops/privacy-shop/orders", json=order)
    _back(app, Order, 100)
    with app.state.session_factory.begin() as db:
        db.execute(update(Upload).where(Upload.id == uuid.UUID(session["id"]))
                   .values(created_at=datetime.now(UTC) - timedelta(days=2)))  # fmt: skip
        counts = sweep(db, app.state.storage)
    assert counts["abandoned"] == 1 and counts["orders"] == 1
    assert c.get("/api/v1/orders").json()["orders"] == []  # older than the 30-day view
    with app.state.session_factory() as db:
        row = db.scalar(select(Order))
        assert row.customer_name is None and row.note is None and row.total_inr > 0


def test_export_has_everything_and_delete_removes_everything(
    app_settings: Settings, clip: bytes
) -> None:
    app = create_app(app_settings)
    with TestClient(app) as c, TestClient(app) as other:
        h = _shop(app, c, clip)
        _shop(app, other, clip, name="Other Shop")
        item = c.get("/api/v1/public/shops/privacy-shop").json()["products"][0]["id"]
        c.post("/api/v1/public/shops/privacy-shop/orders",
               json={"items": [{"id": item, "qty": 1}], "name": "Ravi"})  # fmt: skip

        r = c.get("/api/v1/privacy/export")
        assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        data = json.loads(zf.read("my-shop-data.json"))
        assert data["shop"]["name"] == "Privacy Shop" and len(data["items"]) == 3
        assert data["orders"][0]["customer_name"] == "Ravi"
        assert any(n.startswith("photos/") for n in zf.namelist())
        assert "Other Shop" not in json.dumps(data)

        r = c.post("/api/v1/privacy/delete", json={"confirm": "wrong shop"}, headers=h)
        assert r.status_code == 422 and r.json()["code"] == "confirm_name"
        with app.state.session_factory() as db:
            ws_id = db.scalar(select(Workspace.id).where(Workspace.slug == "privacy-shop"))
        r = c.post("/api/v1/privacy/delete", json={"confirm": "Privacy Shop"}, headers=h)
        assert r.status_code == 200
        assert c.get("/api/v1/me").status_code == 401
        assert c.get("/api/v1/public/shops/privacy-shop").status_code == 404
        assert not app.state.storage.path(f"ws/{ws_id}").exists()
        assert not app.state.storage.path("public/privacy-shop").exists()
        with app.state.session_factory() as db:
            for model in (Workspace, Product, Order, Job, Upload):
                left = db.scalar(select(func.count()).select_from(model)
                                 .where(model.workspace_id == ws_id if model is not Workspace
                                        else Workspace.id == ws_id))  # fmt: skip
                assert left == 0, model.__name__
            audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "privacy.shop_deleted"))
            assert audit is not None and "Privacy" not in json.dumps(audit.meta)
        # The other shop is untouched.
        assert len(other.get("/api/v1/items").json()["items"]) == 2
