"""Offers: a sale lowers prices (old price as MRP) and republishes; ending it puts them back."""

from __future__ import annotations

import io
import json
import shutil
import uuid
import zipfile
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select, update

from shelf.config import Settings
from shelf.core.clock import india_today
from shelf.db.models import AuditEvent, Catalog, Offer, Workspace
from shelf.jobs.worker import Worker
from shelf.main import create_app, pipeline_handlers
from shelf.privacy.retention import Sweeper

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


def _items(c: TestClient) -> dict[str, dict[str, Any]]:
    return {i["id"]: i for i in c.get("/api/v1/items").json()["items"]}


def _offer(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "kind": "diwali",
        "title_en": "Diwali sale",
        "title_hi": "दिवाली सेल",
        "percent_off": 10,
        "scope": "all",
        "ends_on": (india_today() + timedelta(days=3)).isoformat(),
    }
    return {**body, **overrides}


def _less(price: int, percent: int) -> int:
    return max(1, round(price * (100 - percent) / 100))


def test_an_offer_lowers_prices_republishes_and_ending_it_puts_them_back(
    app_and_client: tuple[Any, TestClient], clip: bytes
) -> None:
    app, c = app_and_client
    h = _shop_with_video(app, c, clip)
    before = _items(c)
    assert all(i["on_offer"] is False and i["mrp_inr"] is None for i in before.values())
    version = _public(c)["version"]
    assert _public(c)["offer"] is None

    r = c.post("/api/v1/offers", json=_offer(), headers=h)
    assert r.status_code == 201, r.text
    offer = r.json()["offer"]
    assert r.json()["shop_version"] == version + 1
    assert offer["kind"] == "diwali" and offer["active"] is True and offer["ended_at"] is None
    assert offer["items_count"] == 2 and offer["scope"] == "all" and offer["item_ids"] == []
    assert offer["percent_off"] == 10 and offer["title_hi"] == "दिवाली सेल"

    during = _items(c)
    for iid, item in during.items():
        old = before[iid]["price_inr"]
        assert item["price_inr"] == _less(old, 10) and item["mrp_inr"] == old
        assert item["on_offer"] is True
    shop = _public(c)
    assert shop["version"] == version + 1
    assert shop["offer"] == {"title_en": "Diwali sale", "title_hi": "दिवाली सेल",
                             "percent_off": 10, "ends_on": offer["ends_on"]}  # fmt: skip
    by_public = {i["public_id"]: i for i in before.values()}
    for p in shop["products"]:
        old = by_public[p["id"]]
        assert p["on_offer"] is True and p["price_paise"] == _less(old["price_inr"], 10) * 100
        assert p["mrp_display"] == old["price_display"]
        assert (p["was_inr"], p["was_display"]) == (old["price_inr"], old["price_display"])

    listed = c.get("/api/v1/offers").json()
    assert listed["active"]["id"] == offer["id"] and listed["past"] == []
    assert listed["shop_url"] == "https://shop.example/s/gupta-store"

    # Orders are priced from the published shop, so at the offer price.
    first = shop["products"][0]
    order = c.post("/api/v1/public/shops/gupta-store/orders",
                   json={"items": [{"id": first["id"], "qty": 2}]})  # fmt: skip
    assert order.json()["total_inr"] == 2 * first["price_paise"] // 100

    r = c.post(f"/api/v1/offers/{offer['id']}/end", headers=h)
    assert r.status_code == 200, r.text
    ended = r.json()["offer"]
    assert ended["active"] is False and ended["ended_at"] is not None
    assert r.json()["shop_version"] == version + 2
    after = _items(c)
    for iid, item in after.items():
        assert item["price_inr"] == before[iid]["price_inr"] and item["mrp_inr"] is None
        assert item["on_offer"] is False
    shop = _public(c)
    assert shop["offer"] is None and not any(p["on_offer"] for p in shop["products"])
    assert all(p["mrp_display"] is None for p in shop["products"])
    assert all(p["was_inr"] is None and p["was_display"] is None for p in shop["products"])
    listed = c.get("/api/v1/offers").json()
    assert listed["active"] is None and [o["id"] for o in listed["past"]] == [offer["id"]]

    again = c.post(f"/api/v1/offers/{offer['id']}/end", headers=h)
    assert again.status_code == 409 and again.json()["code"] == "offer_ended"
    with app.state.session_factory() as db:
        actions = db.scalars(select(AuditEvent.action).where(AuditEvent.action.like("offer.%")))
        assert sorted(actions) == ["offer.ended", "offer.started"]


def test_an_announcement_changes_no_prices(
    app_and_client: tuple[Any, TestClient], clip: bytes
) -> None:
    app, c = app_and_client
    h = _shop_with_video(app, c, clip)
    before = _items(c)
    body = _offer(kind="new_stock", title_en="New stock is in", title_hi=None, percent_off=None)
    r = c.post("/api/v1/offers", json=body, headers=h)
    assert r.status_code == 201, r.text
    offer = r.json()["offer"]
    assert offer["percent_off"] is None and offer["items_count"] == 0
    assert offer["title_hi"] is None
    during = _items(c)
    assert all(during[i]["price_inr"] == before[i]["price_inr"] for i in before)
    assert not any(i["on_offer"] for i in during.values())
    shop = _public(c)
    assert shop["offer"]["title_en"] == "New stock is in" and shop["offer"]["percent_off"] is None
    assert not any(p["on_offer"] for p in shop["products"])
    assert c.post(f"/api/v1/offers/{offer['id']}/end", headers=h).status_code == 200
    assert _public(c)["offer"] is None

    # A version published before offers existed has none of the offer fields: they read as null.
    offer_keys = ("on_offer", "was_inr", "was_display")
    with app.state.session_factory.begin() as db:
        latest = db.scalar(select(Catalog).order_by(Catalog.version.desc()).limit(1))
        assert latest is not None
        old = {k: v for k, v in latest.snapshot.items() if k != "offer"}
        old["products"] = [{k: v for k, v in p.items() if k not in offer_keys}
                           for p in old["products"]]  # fmt: skip
        latest.snapshot = old
    shop = _public(c)
    assert shop["offer"] is None and shop["products"]
    assert all((p["on_offer"], p["was_inr"], p["was_display"]) == (False, None, None)
               for p in shop["products"])  # fmt: skip


def test_the_shop_shows_the_price_before_the_offer_not_only_the_printed_mrp(
    app_and_client: tuple[Any, TestClient], clip: bytes
) -> None:
    app, c = app_and_client
    h = _shop_with_video(app, c, clip)
    item = c.post("/api/v1/items", json={"title_en": "Toffee", "price_inr": 4, "mrp_inr": 5},
                  headers=h).json()["item"]  # fmt: skip
    png = io.BytesIO()
    Image.new("RGB", (700, 700), "orange").save(png, "PNG")
    r = c.post(f"/api/v1/items/{item['id']}/photo", content=png.getvalue(),
               headers={**h, "content-type": "image/png"})  # fmt: skip
    assert r.status_code == 200, r.text
    r = c.post("/api/v1/offers", json=_offer(scope="items", item_ids=[item["id"]],
                                             percent_off=25), headers=h)  # fmt: skip
    assert r.status_code == 201, r.text
    toffee = next(p for p in _public(c)["products"] if p["id"] == item["public_id"])
    assert toffee["on_offer"] is True and toffee["price_display"] == "₹3"
    # The printed MRP stays (the Meta feed uses it); "was" is what the shop charged before.
    assert toffee["mrp_display"] == "₹5"
    assert (toffee["was_inr"], toffee["was_display"]) == (4, "₹4")
    others = [p for p in _public(c)["products"] if p["id"] != item["public_id"]]
    assert others and all(p["was_inr"] is None and p["was_display"] is None for p in others)


def test_prices_the_seller_changed_during_the_offer_are_kept(
    app_and_client: tuple[Any, TestClient], clip: bytes
) -> None:
    app, c = app_and_client
    h = _shop_with_video(app, c, clip)
    before = _items(c)
    first, second = list(before)
    offer = c.post("/api/v1/offers", json=_offer(percent_off=20), headers=h).json()["offer"]

    r = c.patch(f"/api/v1/items/{first}", json={"price_inr": 999}, headers=h)
    assert r.json()["item"]["on_offer"] is False
    # An MRP the seller types during the offer stays too, while the price still goes back.
    r = c.patch(f"/api/v1/items/{second}", json={"mrp_inr": 5000}, headers=h)
    assert r.json()["item"]["on_offer"] is True
    added = c.post("/api/v1/items", json={"title_en": "Parle-G 250 g", "price_inr": 25},
                   headers=h).json()["item"]  # fmt: skip
    assert added["on_offer"] is False and added["price_inr"] == 25

    c.post(f"/api/v1/offers/{offer['id']}/end", headers=h)
    after = _items(c)
    assert after[first]["price_inr"] == 999
    assert after[second]["price_inr"] == before[second]["price_inr"]
    assert after[second]["mrp_inr"] == 5000
    assert after[added["id"]]["price_inr"] == 25  # added after the start: never part of it


def test_one_offer_at_a_time_and_the_last_day_cannot_have_passed(
    app_and_client: tuple[Any, TestClient], clip: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, c = app_and_client
    h = _shop_with_video(app, c, clip)
    yesterday = (india_today() - timedelta(days=1)).isoformat()
    r = c.post("/api/v1/offers", json=_offer(ends_on=yesterday), headers=h)
    assert r.status_code == 422 and r.json()["code"] == "ends_on_past"
    for bad in ({"percent_off": 95}, {"percent_off": 0}, {"title_en": "   "},
                {"title_en": "x" * 81}, {"kind": "black_friday"}, {"scope": "shelf"}):  # fmt: skip
        r = c.post("/api/v1/offers", json=_offer(**bad), headers=h)
        assert r.status_code == 422 and r.json()["code"] == "validation_failed", bad

    today = c.post("/api/v1/offers", json=_offer(ends_on=india_today().isoformat()), headers=h)
    assert today.status_code == 201, today.text  # the last day may be today
    r = c.post("/api/v1/offers", json=_offer(kind="weekend", title_en="Weekend sale"), headers=h)
    assert r.status_code == 409 and r.json()["code"] == "offer_running"
    # Two starts that arrive at once both pass the first check; the database stops the second.
    monkeypatch.setattr("shelf.catalog.offers.active_offer", lambda *_: None)
    r = c.post("/api/v1/offers", json=_offer(kind="weekend", title_en="Weekend sale"), headers=h)
    assert r.status_code == 409 and r.json()["code"] == "offer_running"
    monkeypatch.undo()
    assert c.get("/api/v1/offers").json()["active"]["id"] == today.json()["offer"]["id"]


def test_scope_section_and_items(app_and_client: tuple[Any, TestClient], clip: bytes) -> None:
    app, c = app_and_client
    h = _shop_with_video(app, c, clip)
    before = _items(c)
    first, second = list(before)
    for body, code in (
        (_offer(scope="section"), "pick_section"),
        (_offer(scope="items"), "pick_items"),
        (_offer(scope="items", item_ids=[]), "pick_items"),
    ):
        r = c.post("/api/v1/offers", json=body, headers=h)
        assert r.status_code == 422 and r.json()["code"] == code
    r = c.post("/api/v1/offers", json=_offer(scope="items", item_ids=[first, str(uuid.uuid4())]),
               headers=h)  # fmt: skip
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    r = c.post("/api/v1/offers", json=_offer(scope="section", section_id=str(uuid.uuid4())),
               headers=h)  # fmt: skip
    assert r.status_code == 404 and r.json()["code"] == "not_found"

    r = c.post("/api/v1/offers", json=_offer(scope="items", item_ids=[first, first],
                                             percent_off=50, section_id=str(uuid.uuid4())),
               headers=h)  # fmt: skip
    assert r.status_code == 201, r.text
    offer = r.json()["offer"]
    assert offer["item_ids"] == [first] and offer["items_count"] == 1
    assert offer["section_id"] is None  # only used for scope "section"
    during = _items(c)
    assert during[first]["price_inr"] == _less(before[first]["price_inr"], 50)
    assert during[first]["on_offer"] is True
    assert during[second]["price_inr"] == before[second]["price_inr"]
    assert during[second]["on_offer"] is False
    c.post(f"/api/v1/offers/{offer['id']}/end", headers=h)

    festive = c.post("/api/v1/sections", json={"name_en": "Festive picks"}, headers=h).json()
    section = next(s["id"] for s in festive["sections"] if s["name_en"] == "Festive picks")
    c.patch(f"/api/v1/items/{second}", json={"section_id": section}, headers=h)
    r = c.post("/api/v1/offers", json=_offer(scope="section", section_id=section), headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["offer"]["section_id"] == section and r.json()["offer"]["items_count"] == 1
    during = _items(c)
    assert during[second]["on_offer"] is True and during[first]["on_offer"] is False


def test_other_shops_cannot_see_end_or_target_this_shops_offers(
    app_settings: Settings, clip: bytes
) -> None:
    app = create_app(app_settings)
    with TestClient(app) as c, TestClient(app) as intruder:
        h = _shop_with_video(app, c, clip)
        mine = list(_items(c))
        sarees = c.get("/api/v1/sections").json()["sections"][0]["id"]
        offer = c.post("/api/v1/offers", json=_offer(), headers=h).json()["offer"]

        hi = _signin(intruder, "Other Shop")
        listed = intruder.get("/api/v1/offers").json()
        assert listed == {"active": None, "past": [], "shop_url": None}
        r = intruder.post(f"/api/v1/offers/{offer['id']}/end", headers=hi)
        assert r.status_code == 404 and r.json()["code"] == "not_found"
        r = intruder.post("/api/v1/offers", json=_offer(scope="items", item_ids=mine), headers=hi)
        assert r.status_code == 404 and r.json()["code"] == "not_found"
        r = intruder.post("/api/v1/offers", json=_offer(scope="section", section_id=sarees),
                          headers=hi)  # fmt: skip
        assert r.status_code == 404 and r.json()["code"] == "not_found"
        # Without the CSRF header nothing ends either.
        assert c.post(f"/api/v1/offers/{offer['id']}/end").status_code == 403
        assert c.get("/api/v1/offers").json()["active"]["id"] == offer["id"]


def test_offers_past_their_last_day_end_on_their_own(
    app_and_client: tuple[Any, TestClient], app_settings: Settings, clip: bytes
) -> None:
    app, c = app_and_client
    h = _shop_with_video(app, c, clip)
    before = _items(c)
    offer = c.post("/api/v1/offers", json=_offer(ends_on=india_today().isoformat()),
                   headers=h).json()["offer"]  # fmt: skip
    sweeper = Sweeper(app.state.session_factory, app.state.storage, app_settings)
    assert sweeper.run_once()["offers"] == 0  # today is still its last day

    with app.state.session_factory.begin() as db:
        db.execute(update(Offer).values(ends_on=india_today() - timedelta(days=1)))
    version = _public(c)["version"]
    assert sweeper.run_once()["offers"] == 1
    after = _items(c)
    assert all(after[i]["price_inr"] == before[i]["price_inr"] for i in before)
    assert not any(i["on_offer"] for i in after.values())
    shop = _public(c)
    assert shop["offer"] is None and shop["version"] == version + 1
    listed = c.get("/api/v1/offers").json()
    assert listed["active"] is None and listed["past"][0]["id"] == offer["id"]
    with app.state.session_factory() as db:
        audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "offer.ended"))
        assert audit is not None and audit.actor == "system" and audit.meta["automatic"] is True


def test_a_due_offer_does_not_block_the_next_one(
    app_and_client: tuple[Any, TestClient], clip: bytes
) -> None:
    app, c = app_and_client
    h = _shop_with_video(app, c, clip)
    before = _items(c)
    old = c.post("/api/v1/offers", json=_offer(), headers=h).json()["offer"]
    with app.state.session_factory.begin() as db:
        db.execute(update(Offer).values(ends_on=india_today() - timedelta(days=1)))
    # The hourly sweep has not run yet: starting the next offer ends this one first.
    r = c.post("/api/v1/offers", json=_offer(kind="clearance", title_en="Clearance",
                                             percent_off=30), headers=h)  # fmt: skip
    assert r.status_code == 201, r.text
    for iid, item in _items(c).items():
        assert item["price_inr"] == _less(before[iid]["price_inr"], 30)
        assert item["mrp_inr"] == before[iid]["price_inr"]
    listed = c.get("/api/v1/offers").json()
    assert listed["active"]["title_en"] == "Clearance"
    assert [o["id"] for o in listed["past"]] == [old["id"]]


def test_an_offer_on_a_shop_not_yet_published(app_and_client: tuple[Any, TestClient]) -> None:
    _, c = app_and_client
    h = _signin(c)
    r = c.post("/api/v1/offers", json=_offer(), headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["shop_version"] is None and r.json()["offer"]["items_count"] == 0
    assert c.get("/api/v1/offers").json()["shop_url"] is None
    r = c.post(f"/api/v1/offers/{r.json()['offer']['id']}/end", headers=h)
    assert r.status_code == 200 and r.json()["shop_version"] is None


def test_export_has_offers_and_deleting_the_shop_removes_them(
    app_and_client: tuple[Any, TestClient], clip: bytes
) -> None:
    app, c = app_and_client
    h = _shop_with_video(app, c, clip)
    c.post("/api/v1/offers", json=_offer(), headers=h)
    zf = zipfile.ZipFile(io.BytesIO(c.get("/api/v1/privacy/export").content))
    data = json.loads(zf.read("my-shop-data.json"))
    assert [o["title_en"] for o in data["offers"]] == ["Diwali sale"]
    assert len(data["offers"][0]["price_changes"]) == 2

    with app.state.session_factory() as db:
        ws_id = db.scalar(select(Workspace.id).where(Workspace.slug == "gupta-store"))
    r = c.post("/api/v1/privacy/delete", json={"confirm": "gupta-store"}, headers=h)
    assert r.status_code == 200, r.text
    with app.state.session_factory() as db:
        left = db.scalar(select(func.count()).select_from(Offer).where(Offer.workspace_id == ws_id))
        assert left == 0
