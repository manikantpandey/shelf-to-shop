"""Running a shop: sections, bulk edits, items added by hand, profile, MRP and basket orders."""

from __future__ import annotations

import csv
import io
import shutil
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from shelf.config import Settings
from shelf.jobs.worker import Worker
from shelf.main import create_app, pipeline_handlers

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _signin(c: TestClient, name: str = "Gupta Store") -> dict[str, str]:
    assert c.post("/api/v1/auth/demo", json={"shop_name": name}).status_code == 200
    return {"x-csrf-token": c.cookies["sts_csrf"]}


def _shop_with_video(
    app: Any, c: TestClient, clip: bytes, name: str = "Gupta Store"
) -> dict[str, str]:
    h = _signin(c, name)
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


def _public(c: TestClient, slug: str = "gupta-store") -> dict[str, Any]:
    r = c.get(f"/api/v1/public/shops/{slug}")
    assert r.status_code == 200, r.text
    return dict(r.json())


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (700, 700), "orange").save(buf, "PNG")
    return buf.getvalue()


def test_sections_are_made_from_categories_and_can_be_arranged(
    app_and_client: tuple[Any, TestClient], clip: bytes
) -> None:
    app, c = app_and_client
    h = _shop_with_video(app, c, clip)
    sections = c.get("/api/v1/sections").json()["sections"]
    assert [s["name_en"] for s in sections] == ["Sarees"]
    assert sections[0]["items"] == 2
    shop = _public(c)
    assert [s["name_en"] for s in shop["sections"]] == ["Sarees"]
    assert all(p["section"] == sections[0]["id"] for p in shop["products"])

    sarees = sections[0]["id"]
    c.patch(f"/api/v1/sections/{sarees}", json={"name_en": "Silk sarees", "name_hi": "सिल्क साड़ी"},
            headers=h)  # fmt: skip
    new = c.post("/api/v1/sections", json={"name_en": "Festive picks"}, headers=h).json()
    festive = next(s["id"] for s in new["sections"] if s["name_en"] == "Festive picks")
    order = c.post("/api/v1/sections/order", json={"ids": [festive, sarees]}, headers=h).json()
    assert [s["name_en"] for s in order["sections"]] == ["Festive picks", "Silk sarees"]

    item = c.get("/api/v1/items").json()["items"][0]
    c.patch(f"/api/v1/items/{item['id']}", json={"section_id": festive, "featured": True},
            headers=h)  # fmt: skip
    shop = _public(c)
    # Section names and order come live from the seller's settings.
    assert [s["name_en"] for s in shop["sections"]] == ["Festive picks", "Silk sarees"]
    assert shop["products"][0]["id"] == item["public_id"] and shop["products"][0]["featured"]

    # A section with items can only go once its items have somewhere to move.
    r = c.delete(f"/api/v1/sections/{festive}", headers=h)
    assert r.status_code == 422 and r.json()["code"] == "pick_section"
    r = c.delete(f"/api/v1/sections/{festive}", params={"move_to": sarees}, headers=h)
    assert [s["name_en"] for s in r.json()["sections"]] == ["Silk sarees"]
    assert r.json()["sections"][0]["items"] == 2


def test_bulk_edits_republish_once(app_and_client: tuple[Any, TestClient], clip: bytes) -> None:
    app, c = app_and_client
    h = _shop_with_video(app, c, clip)
    items = c.get("/api/v1/items").json()["items"]
    ids = [i["id"] for i in items]
    before = {i["id"]: i["price_inr"] for i in items}
    version = _public(c)["version"]

    r = c.post("/api/v1/items/bulk", json={"ids": ids, "action": "price_add", "value": 10},
               headers=h)  # fmt: skip
    assert r.status_code == 200 and r.json()["shop_version"] == version + 1
    after = {i["id"]: i["price_inr"] for i in r.json()["items"]}
    assert after == {k: v + 10 for k, v in before.items()}
    r = c.post("/api/v1/items/bulk", json={"ids": ids[:1], "action": "price_percent", "value": -50},
               headers=h)  # fmt: skip
    assert r.json()["items"][0]["price_inr"] == round((before[ids[0]] + 10) / 2)
    c.post("/api/v1/items/bulk", json={"ids": ids[:1], "action": "sold_out"}, headers=h)
    c.post("/api/v1/items/bulk", json={"ids": ids[1:], "action": "hide"}, headers=h)
    shop = _public(c)
    assert [p["sold_out"] for p in shop["products"]] == [True]  # the hidden one is gone
    r = c.post("/api/v1/items/bulk", json={"ids": ids, "action": "price_add"}, headers=h)
    assert r.status_code == 422 and r.json()["code"] == "value_required"


def test_items_added_by_hand_go_live_with_a_photo(
    app_and_client: tuple[Any, TestClient], clip: bytes
) -> None:
    app, c = app_and_client
    h = _shop_with_video(app, c, clip)
    r = c.post("/api/v1/items", json={"title_en": "Parle-G 250 g", "price_inr": 25, "mrp_inr": 30},
               headers=h)  # fmt: skip
    assert r.status_code == 201, r.text
    item = r.json()["item"]
    assert item["from_video"] is False and item["live"] is False  # no photo yet
    assert len(_public(c)["products"]) == 2

    r = c.post(f"/api/v1/items/{item['id']}/photo", content=_png(),
               headers={**h, "content-type": "image/png"})  # fmt: skip
    assert r.status_code == 200 and r.json()["item"]["live"] is True
    shop = _public(c)
    added = next(p for p in shop["products"] if p["id"] == item["public_id"])
    assert (added["price_display"], added["mrp_display"]) == ("₹25", "₹30")
    rows = {
        row["id"]: row
        for row in csv.DictReader(io.StringIO(c.get("/api/v1/catalog/feed.csv").text))
    }
    assert (rows[item["public_id"]]["price"], rows[item["public_id"]]["sale_price"]) == (
        "30.00 INR", "25.00 INR")  # fmt: skip
    # Items added by hand are not a video: the history only lists recordings.
    assert len(c.get("/api/v1/videos").json()["videos"]) == 1
    assert c.get(f"/api/v1/items/{item['id']}/moments").status_code == 410


def test_shop_profile_and_logo_show_on_the_shop_page(
    app_and_client: tuple[Any, TestClient], clip: bytes
) -> None:
    app, c = app_and_client
    h = _shop_with_video(app, c, clip)
    r = c.patch("/api/v1/profile", json={"upi_id": "not a upi"}, headers=h)
    assert r.status_code == 422
    r = c.patch("/api/v1/profile", headers=h, json={
        "hours": "8 am to 10 pm", "delivery": "both", "delivery_note": "Free within 2 km",
        "min_order_inr": 100, "upi_id": "gupta.store@okaxis", "about": "Family shop since 1998.",
        "notice": "Diwali offer: free delivery",
    })  # fmt: skip
    assert r.status_code == 200, r.text
    profile = _public(c)["profile"]
    assert profile["hours"] == "8 am to 10 pm" and profile["delivery"] == "both"
    assert profile["upi_id"] == "gupta.store@okaxis" and profile["logo_url"] is None
    r = c.post("/api/v1/profile/logo", content=_png(), headers={**h, "content-type": "image/png"})
    assert r.status_code == 200, r.text
    logo = _public(c)["profile"]["logo_url"]
    assert c.get(urlsplit(logo).path).headers["content-type"] == "image/jpeg"
    # Clearing a field: an empty string removes it.
    c.patch("/api/v1/profile", json={"notice": "", "min_order_inr": 0}, headers=h)
    profile = _public(c)["profile"]
    assert profile["notice"] is None and profile["min_order_inr"] is None


def test_basket_orders_are_priced_by_the_shop_and_land_in_the_order_book(
    app_settings: Settings, clip: bytes
) -> None:
    app = create_app(app_settings)
    with TestClient(app) as c, TestClient(app) as buyer, TestClient(app) as intruder:
        h = _shop_with_video(app, c, clip)
        shop = _public(buyer)
        first, second = shop["products"][0], shop["products"][1]
        r = buyer.post("/api/v1/public/shops/gupta-store/orders", json={
            "items": [{"id": first["id"], "qty": 2}, {"id": second["id"], "qty": 1},
                      {"id": first["id"], "qty": 1}],
            "name": "Ravi", "note": "Near the temple www.spam.example",
            "price_inr": 1,  # ignored: prices come from the shop
        })  # fmt: skip
        assert r.status_code == 201, r.text
        order = r.json()
        total = 3 * first["price_paise"] // 100 + second["price_paise"] // 100
        assert order["number"] == 1 and order["total_inr"] == total
        link = urlsplit(order["whatsapp_url"])
        assert link.netloc == "wa.me" and link.path == "/919876543210"
        text = parse_qs(link.query)["text"][0]
        assert text.startswith("Order #1 for Gupta Store") and "3 x" in text and "Ravi" in text
        assert "spam" not in text

        r = buyer.post("/api/v1/public/shops/gupta-store/orders",
                       json={"items": [{"id": second["id"], "qty": 1}], "lang": "hi"})  # fmt: skip
        assert r.json()["number"] == 2
        assert "के लिए ऑर्डर #2" in parse_qs(urlsplit(r.json()["whatsapp_url"]).query)["text"][0]
        bad = buyer.post("/api/v1/public/shops/gupta-store/orders",
                         json={"items": [{"id": "gupta-store-nope", "qty": 1}]})  # fmt: skip
        assert bad.status_code == 409 and bad.json()["code"] == "item_gone"

        items = c.get("/api/v1/items").json()["items"]
        c.patch(f"/api/v1/items/{items[0]['id']}", json={"sold_out": True}, headers=h)
        sold = buyer.post("/api/v1/public/shops/gupta-store/orders",
                          json={"items": [{"id": items[0]["public_id"], "qty": 1}]})  # fmt: skip
        assert sold.status_code == 409 and sold.json()["code"] == "sold_out"

        book = c.get("/api/v1/orders").json()
        assert [o["number"] for o in book["orders"]] == [2, 1]
        assert book["summary"]["counts"]["new"] == 2 and book["summary"]["today_orders"] == 2
        assert book["orders"][1]["customer_name"] == "Ravi"
        oid = book["orders"][1]["id"]
        r = c.patch(f"/api/v1/orders/{oid}", json={"status": "delivered", "paid": True}, headers=h)
        assert (
            r.json()["order"]["status"] == "delivered"
            and r.json()["summary"]["today_paid_inr"] == total
        )
        assert c.get("/api/v1/stats").json()["orders"]["today_orders"] == 2

        hi = _signin(intruder, "Other Shop")
        assert intruder.get("/api/v1/orders").json()["orders"] == []
        r = intruder.patch(f"/api/v1/orders/{oid}", json={"paid": False}, headers=hi)
        assert r.status_code == 404
        assert intruder.get("/api/v1/sections").json()["sections"] == []
        r = intruder.post("/api/v1/items/bulk", json={"ids": [items[1]["id"]], "action": "hide"},
                          headers=hi)  # fmt: skip
        assert r.status_code == 404
