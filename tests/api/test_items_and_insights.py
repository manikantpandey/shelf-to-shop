"""Items across videos, replacement photos, shop stats, run details and the demo sample shop."""

from __future__ import annotations

import csv
import io
import shutil
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, update

from shelf.config import Settings
from shelf.db.models import Workspace
from shelf.jobs.worker import Worker
from shelf.main import create_app, pipeline_handlers

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _signin(c: TestClient, **body: Any) -> dict[str, str]:
    r = c.post("/api/v1/auth/demo", json=body or {"shop_name": "Gupta Store"})
    assert r.status_code == 200, r.text
    return {"x-csrf-token": c.cookies["sts_csrf"]}


def _published_video(app: Any, c: TestClient, h: dict[str, str], clip: bytes) -> str:
    """Upload, process and publish one video; returns the job id."""
    if c.get("/api/v1/me").json()["workspace"]["whatsapp"] is None:
        c.patch("/api/v1/workspace", json={"whatsapp": "98765 43210"}, headers=h)
        c.post("/api/v1/consents/recording", headers=h)
    upload = c.post("/api/v1/uploads", content=clip, headers={**h, "content-type": "video/mp4"})
    job = c.post("/api/v1/jobs", json={"upload_id": upload.json()["id"]}, headers=h).json()
    assert Worker(app.state.session_factory, pipeline_handlers(app), worker_id="t").run_once()
    review = c.get(f"/api/v1/jobs/{job['id']}/review").json()
    for flag in review["flags"]:
        action = {"action": "remove_item"} if flag["kind"] == "missing_price" else {
            "action": "dismiss"}  # fmt: skip
        c.post(f"/api/v1/jobs/{job['id']}/flags/{flag['id']}/resolve", json=action, headers=h)
    r = c.post(f"/api/v1/jobs/{job['id']}/publish", headers=h)
    assert r.status_code == 200, r.text
    return str(job["id"])


def _shop(c: TestClient, slug: str = "gupta-store") -> dict[str, Any]:
    r = c.get(f"/api/v1/public/shops/{slug}")
    assert r.status_code == 200, r.text
    return dict(r.json())


def _png(size: tuple[int, int] = (800, 600)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", size, (200, 30, 30, 255)).save(buf, "PNG")
    return buf.getvalue()


def test_shop_holds_items_from_every_video_and_edits_republish(
    app_and_client: tuple[Any, TestClient], clip: bytes
) -> None:
    app, c = app_and_client
    h = _signin(c)
    _published_video(app, c, h, clip)
    assert len(_shop(c)["products"]) == 2
    _published_video(app, c, h, clip)
    shop = _shop(c)
    assert len(shop["products"]) == 4 and len({p["id"] for p in shop["products"]}) == 4

    items = c.get("/api/v1/items").json()["items"]
    assert len(items) == 4 and all(i["live"] for i in items)
    first = items[0]
    version = shop["version"]

    r = c.patch(f"/api/v1/items/{first['id']}", json={"sold_out": True, "price_inr": 999},
                headers=h)  # fmt: skip
    assert r.status_code == 200, r.text
    assert r.json()["shop_version"] == version + 1
    shop = _shop(c)
    sold = next(p for p in shop["products"] if p["id"] == first["public_id"])
    assert sold["sold_out"] is True and sold["price_display"] == "₹999"
    feed = {r["id"]: r for r in csv.DictReader(io.StringIO(c.get("/api/v1/catalog/feed.csv").text))}
    assert feed[first["public_id"]]["availability"] == "out of stock"

    c.patch(f"/api/v1/items/{first['id']}", json={"removed": True}, headers=h)
    assert first["public_id"] not in {p["id"] for p in _shop(c)["products"]}
    assert len(c.get("/api/v1/items").json()["items"]) == 3


def test_seller_photo_upload_replaces_the_cut_out(
    app_and_client: tuple[Any, TestClient], clip: bytes
) -> None:
    app, c = app_and_client
    h = _signin(c)
    _published_video(app, c, h, clip)
    item = c.get("/api/v1/items").json()["items"][0]

    r = c.post(f"/api/v1/items/{item['id']}/photo", content=b"GIF89a not really",
               headers={**h, "content-type": "image/gif"})  # fmt: skip
    assert r.status_code == 422 and r.json()["code"] == "not_a_photo"
    r = c.post(f"/api/v1/items/{item['id']}/photo", content=_png(),
               headers={**h, "content-type": "image/png"})  # fmt: skip
    assert r.status_code == 200, r.text
    assert r.json()["item"]["image_source"] == "upload"
    assert r.json()["item"]["ai_background"] is False

    photo = c.get(r.json()["item"]["image_url"])
    with Image.open(io.BytesIO(photo.content)) as im:
        assert im.size == (1024, 1024) and im.format == "JPEG"
        assert not im.getexif()  # no camera data or location
    live = next(p for p in _shop(c)["products"] if p["id"] == item["public_id"])
    assert live["ai_background"] is False


def test_pick_a_better_moment_from_the_video(
    app_and_client: tuple[Any, TestClient], clip: bytes
) -> None:
    app, c = app_and_client
    h = _signin(c)
    _published_video(app, c, h, clip)
    item = c.get("/api/v1/items").json()["items"][0]

    moments = c.get(f"/api/v1/items/{item['id']}/moments").json()["moments"]
    assert 1 < len(moments) <= 6
    assert all(0 <= m["t_s"] <= 8 for m in moments)
    assert c.get(moments[0]["image_url"]).headers["content-type"] == "image/jpeg"

    r = c.post(f"/api/v1/items/{item['id']}/photo/moment", json={"i": 1, "x": 0.5, "y": 0.5},
               headers=h)  # fmt: skip
    assert r.status_code == 200, r.text
    assert r.json()["item"]["image_source"] == "frame"
    details = c.get(f"/api/v1/jobs/{item['job_id']}/details").json()
    assert any(s["stage"] == "recut" and s["calls"] == 1 for s in details["stages"])


OFF_HIT = {
    "code": "8902080204052",
    "product_name": "Mirinda orange Flavour 750ml",
    "brands": ["Mirinda"],
    "countries_tags": ["en:india"],
    "image_front_url": (
        "https://images.openfoodfacts.org/images/products/890/208/020/4052/front_en.7.400.jpg"
    ),
}


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (900, 1200), "orange").save(buf, "JPEG")
    return buf.getvalue()


def test_pack_photo_from_open_food_facts(
    app_and_client: tuple[Any, TestClient], clip: bytes
) -> None:
    app, c = app_and_client
    h = _signin(c)
    _published_video(app, c, h, clip)
    item = c.get("/api/v1/items").json()["items"][0]

    with respx.mock(assert_all_called=False) as mock:
        mock.get("https://search.openfoodfacts.org/search").mock(
            return_value=httpx.Response(200, json={"hits": [OFF_HIT, {"code": "x"}]})
        )
        product = mock.get(
            "https://world.openfoodfacts.org/api/v2/product/8902080204052.json"
        ).mock(return_value=httpx.Response(200, json={"status": 1, "product": OFF_HIT}))
        full = mock.get(
            "https://images.openfoodfacts.org/images/products/890/208/020/4052/front_en.7.full.jpg"
        ).mock(return_value=httpx.Response(200, content=_jpeg()))

        found = c.get("/api/v1/photos/search", params={"q": "mirinda orange"}).json()
        assert [r["code"] for r in found["results"]] == ["8902080204052"]
        assert "CC BY-SA" in found["credit"]
        assert c.get("/api/v1/photos/search", params={"barcode": "12ab"}).status_code == 422

        r = c.post(f"/api/v1/items/{item['id']}/photo/pack", json={"code": "8902080204052"},
                   headers=h)  # fmt: skip
        assert r.status_code == 200, r.text
        assert product.called and full.called
    assert r.json()["item"]["image_source"] == "openfoodfacts"
    live = next(p for p in _shop(c)["products"] if p["id"] == item["public_id"])
    assert "Open Food Facts" in live["image_credit"]
    assert live["image_credit_url"] == "https://world.openfoodfacts.org/product/8902080204052"


def test_shop_stats_count_views_and_order_taps(
    app_and_client: tuple[Any, TestClient], clip: bytes
) -> None:
    app, c = app_and_client
    h = _signin(c)
    _published_video(app, c, h, clip)
    item = _shop(c)["products"][0]["id"]

    for _ in range(3):
        assert (
            c.post("/api/v1/public/shops/gupta-store/events", json={"kind": "view"}).status_code
            == 204
        )
    for _ in range(2):
        r = c.post("/api/v1/public/shops/gupta-store/events", json={"kind": "order", "item": item})
        assert r.status_code == 204
    r = c.post("/api/v1/public/shops/gupta-store/events", json={"kind": "order", "item": "nope"})
    assert r.status_code == 404
    assert c.post("/api/v1/public/shops/nobody/events", json={"kind": "view"}).status_code == 404

    stats = c.get("/api/v1/stats").json()
    assert stats["views_7d"] == 3 and stats["orders_7d"] == 2
    assert stats["top_items"][0]["id"] == item and stats["top_items"][0]["orders"] == 2
    assert stats["items_live"] == 2 and stats["videos"] == 1
    assert len(stats["by_day"]) == 7 and stats["by_day"][-1]["views"] == 3

    videos = c.get("/api/v1/videos").json()["videos"]
    assert videos[0]["status"] == "published" and videos[0]["items"] == 2
    assert videos[0]["thumb_url"] and videos[0]["duration_s"] == pytest.approx(8, abs=0.5)
    details = c.get(f"/api/v1/jobs/{videos[0]['id']}/details").json()
    assert [s["stage"] for s in details["stages"]][:2] == ["ingest", "detect"]
    assert sum(s["calls"] for s in details["stages"]) > 0
    assert details["items"][0]["evidence"]
    frame = c.get(details["items"][0]["frame_url"])
    assert frame.status_code == 200 and frame.headers["content-type"] == "image/jpeg"


def test_new_endpoints_are_scoped_to_the_workspace(app_settings: Settings, clip: bytes) -> None:
    app = create_app(app_settings)
    with TestClient(app) as owner, TestClient(app) as intruder:
        h = _signin(owner)
        job_id = _published_video(app, owner, h, clip)
        item = owner.get("/api/v1/items").json()["items"][0]["id"]
        hi = _signin(intruder, shop_name="Other Shop")
        assert intruder.get("/api/v1/items").json()["items"] == []
        assert intruder.get("/api/v1/videos").json()["videos"] == []
        for method, path, kwargs in [
            ("patch", f"/api/v1/items/{item}", {"json": {"sold_out": True}}),
            ("post", f"/api/v1/items/{item}/photo", {"content": _png()}),
            ("get", f"/api/v1/items/{item}/moments", {}),
            ("post", f"/api/v1/items/{item}/photo/moment", {"json": {"i": 0, "x": 0.5, "y": 0.5}}),
            ("get", f"/api/v1/jobs/{job_id}/details", {}),
            ("get", f"/api/v1/jobs/{job_id}/frames/1", {}),
        ]:
            r = getattr(intruder, method)(path, headers=hi, **kwargs)
            assert r.status_code == 404, (path, r.status_code)


def test_demo_sign_in_gets_a_private_copy_of_the_sample_shop(
    app_settings: Settings, clip: bytes
) -> None:
    app = create_app(app_settings)
    with TestClient(app) as builder:
        h = _signin(builder, shop_name="Sample Kirana")
        _published_video(app, builder, h, clip)
        with app.state.session_factory.begin() as db:
            db.execute(update(Workspace).where(Workspace.slug == "sample-kirana")
                       .values(is_template=True))  # fmt: skip
        # The template itself is never a public shop.
        assert builder.get("/api/v1/public/shops/sample-kirana").status_code == 404

    with TestClient(app) as a, TestClient(app) as b:
        ha = _signin(a, sample=True)
        _signin(b, sample=True)
        slug_a = a.get("/api/v1/me").json()["workspace"]["slug"]
        slug_b = b.get("/api/v1/me").json()["workspace"]["slug"]
        assert slug_a != slug_b and slug_a.startswith("sample-kirana-")
        items_a = a.get("/api/v1/items").json()["items"]
        assert len(items_a) == 2 and all(i["live"] for i in items_a)
        assert a.get(items_a[0]["image_url"]).status_code == 200
        assert len(a.get("/api/v1/videos").json()["videos"]) == 1
        assert len(_shop(a, slug_a)["products"]) == 2

        # One visitor's edit never reaches the other copy or the template.
        a.patch(f"/api/v1/items/{items_a[0]['id']}", json={"removed": True}, headers=ha)
        assert len(b.get("/api/v1/items").json()["items"]) == 2
        assert len(_shop(b, slug_b)["products"]) == 2
    with app.state.session_factory() as db:
        assert db.scalar(select(Workspace).where(Workspace.slug == "sample-kirana")).is_template
