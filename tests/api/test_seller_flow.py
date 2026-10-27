"""The seller journey through the API with fake providers, plus the security boundaries."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shelf.config import Settings
from shelf.jobs.worker import Worker
from shelf.main import create_app, pipeline_handlers

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _signin(c: TestClient, name: str = "Sharma Sarees") -> dict[str, str]:
    r = c.post("/api/v1/auth/demo", json={"shop_name": name})
    assert r.status_code == 200, r.text
    return {"x-csrf-token": c.cookies["sts_csrf"]}


def test_full_seller_journey(app_and_client: tuple[Any, TestClient], clip: bytes) -> None:
    app, c = app_and_client
    assert c.get("/api/v1/me").status_code == 401
    h = _signin(c)
    assert c.get("/api/v1/me").json()["workspace"]["slug"] == "sharma-sarees"

    # CSRF: a state-changing request without the header is refused.
    assert c.post("/api/v1/consents/recording").json()["code"] == "csrf_failed"
    # Consent comes before the first recording.
    r = c.post("/api/v1/uploads", content=clip, headers={**h, "content-type": "video/mp4"})
    assert r.json()["code"] == "consent_required"
    assert c.post("/api/v1/consents/recording", headers=h).status_code == 200
    # Content is sniffed, not trusted by name or type.
    r = c.post("/api/v1/uploads", content=b"not a video " * 100,
               headers={**h, "content-type": "video/mp4"})  # fmt: skip
    assert r.status_code == 422 and r.json()["code"] == "not_a_video"
    r = c.post("/api/v1/uploads", content=clip, headers={**h, "content-type": "video/mp4"})
    assert r.status_code == 201, r.text
    upload_id = r.json()["id"]

    job = c.post("/api/v1/jobs", json={"upload_id": upload_id}, headers=h).json()
    assert job["status"] == "queued"
    worker = Worker(app.state.session_factory, pipeline_handlers(app), worker_id="test")
    assert worker.run_once()
    job = c.get(f"/api/v1/jobs/{job['id']}").json()
    assert job["status"] == "needs_review", job
    assert set(job["stages"].values()) == {"done"}

    review = c.get(f"/api/v1/jobs/{job['id']}/review").json()
    prices = {p["idx"]: p["price_inr"] for p in review["products"]}
    assert prices == {1: 1200, 2: 850, 3: None}
    flags = {(f["kind"], f["product_idx"]): f for f in review["flags"]}
    assert ("price_conflict", 2) in flags and ("missing_price", 3) in flags
    img = c.get(review["products"][0]["image_url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"

    # Publishing needs a WhatsApp number and every question answered.
    r = c.post(f"/api/v1/jobs/{job['id']}/publish", headers=h)
    assert r.json()["code"] == "whatsapp_missing"
    assert c.patch("/api/v1/workspace", json={"whatsapp": "12345"}, headers=h).status_code == 422
    c.patch("/api/v1/workspace", json={"whatsapp": "98765 43210"}, headers=h)
    r = c.post(f"/api/v1/jobs/{job['id']}/publish", headers=h)
    assert r.json()["code"] == "questions_open" and r.json()["open_flags"] == 2

    conflict = flags[("price_conflict", 2)]
    r = c.post(f"/api/v1/jobs/{job['id']}/flags/{conflict['id']}/resolve",
               json={"action": "set_price", "price_inr": 850}, headers=h)  # fmt: skip
    assert r.json()["status"] == "resolved"
    missing = flags[("missing_price", 3)]
    c.post(f"/api/v1/jobs/{job['id']}/flags/{missing['id']}/resolve",
           json={"action": "remove_item"}, headers=h)  # fmt: skip
    r = c.post(f"/api/v1/jobs/{job['id']}/publish", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["url"] == "https://shop.example/s/sharma-sarees"

    shop = c.get("/api/v1/public/shops/sharma-sarees").json()
    assert [p["price_display"] for p in shop["products"]] == ["₹1,200", "₹850"]
    raw = json.dumps(shop)
    for private in ("workspace_id", "job", "idx", "evidence", "storage", "confidence", "@"):
        assert private not in raw
    photo = shop["products"][0]["image_url"].replace("https://shop.example", "")
    assert c.get(photo).headers["content-type"] == "image/jpeg"
    feed = c.get("/api/v1/catalog/feed.csv").text
    assert "1200.00 INR" in feed and "850.00 INR" in feed

    assert c.post("/api/v1/auth/logout", headers=h).status_code == 200
    assert c.get("/api/v1/me").status_code == 401


def test_other_workspaces_see_nothing(
    app_and_client: tuple[Any, TestClient], app_settings: Settings, clip: bytes
) -> None:
    app, owner = app_and_client
    h = _signin(owner, "Owner Shop")
    owner.post("/api/v1/consents/recording", headers=h)
    upload_id = owner.post("/api/v1/uploads", content=clip,
                           headers={**h, "content-type": "video/mp4"}).json()["id"]  # fmt: skip
    job_id = owner.post("/api/v1/jobs", json={"upload_id": upload_id}, headers=h).json()["id"]
    Worker(app.state.session_factory, pipeline_handlers(app), worker_id="t").run_once()

    with TestClient(app) as intruder:
        hi = _signin(intruder, "Other Shop")
        for method, url, body in [
            ("get", f"/api/v1/jobs/{job_id}", None),
            ("get", f"/api/v1/jobs/{job_id}/review", None),
            ("get", f"/api/v1/jobs/{job_id}/images/1", None),
            ("patch", f"/api/v1/jobs/{job_id}/products/1", {"price_inr": 1}),
            ("post", f"/api/v1/jobs/{job_id}/publish", None),
            ("post", f"/api/v1/jobs/{job_id}/retry", None),
            ("post", "/api/v1/jobs", {"upload_id": upload_id}),
        ]:
            r = intruder.request(method.upper(), url, json=body, headers=hi)
            assert r.status_code == 404, (method, url, r.status_code)
        assert intruder.get("/api/v1/jobs").json()["jobs"] == []


def test_public_endpoints_reject_bad_paths(app_and_client: tuple[Any, TestClient]) -> None:
    _, c = app_and_client
    assert c.get("/api/v1/public/shops/no-such-shop").status_code == 404
    assert c.get("/api/v1/public/shops/..%2f..%2fetc").status_code == 404
    assert c.get("/api/v1/public/media/x/v1/..%2Fapp.db").status_code == 404
    assert c.get("/api/v1/public/media/x/v1/secret.png").status_code == 404


def test_demo_login_can_be_switched_off(app_settings: Settings) -> None:
    app = create_app(app_settings.model_copy(update={"demo_login_enabled": False}))
    with TestClient(app) as c:
        assert c.post("/api/v1/auth/demo", json={"shop_name": "X shop"}).status_code == 404
