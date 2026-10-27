from __future__ import annotations

import csv
import io
import json
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from engine.export.categories import FB_CATEGORIES
from engine.export.feed import FEED_COLUMNS, FeedInvalidError, FeedItem, build_feed_csv
from engine.export.text import clean_text
from engine.export.whatsapp import (
    InvalidWhatsAppNumberError,
    normalise_number,
    order_link,
    order_message,
)


def item(**kw: Any) -> FeedItem:
    base: dict[str, Any] = {
        "id": "sharma-sarees-blue-01",
        "title": "Blue cotton saree with gold border",
        "description": "Soft handloom cotton saree in deep blue with a thin gold border.",
        "price_paise": 120000,
        "link": "https://shelf.example/s/sharma-sarees/p/blue-01",
        "image_link": "https://media.shelf.example/p/blue-01.jpg",
        "brand": "Sharma Sarees",
        "fb_product_category": FB_CATEGORIES["saree"][0],
        "color": "blue",
        "material": "cotton",
    }
    return FeedItem(**(base | kw))


def rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def test_feed_has_required_columns_and_formats() -> None:
    text, warnings = build_feed_csv([item(), item(id="red-02", additional_image_links=[
        "https://media.shelf.example/a.jpg", "https://media.shelf.example/b.jpg"])])  # fmt: skip
    assert text.splitlines()[0] == ",".join(FEED_COLUMNS)
    first, second = rows(text)
    assert first["price"] == "1200.00 INR"
    assert first["availability"] == "in stock"
    assert first["condition"] == "new"
    assert first["fb_product_category"] == "455"
    # A comma-separated list in one cell must be double-quoted.
    assert '"https://media.shelf.example/a.jpg,https://media.shelf.example/b.jpg"' in text
    assert second["additional_image_link"].count("https://") == 2
    assert warnings == []


@pytest.mark.parametrize(
    ("kw", "field"),
    [
        ({"id": "has space"}, "id"),
        ({"title": ""}, "title"),
        ({"title": "x" * 201}, "title"),
        ({"description": "<b>bold</b> saree"}, "description"),
        ({"description": "order at www.example.com today"}, "description"),
        ({"description": "BEST SAREE IN TOWN BUY NOW"}, "description"),
        ({"price_paise": 0}, "price"),
        ({"link": "http://shelf.example/p"}, "link"),
        ({"image_link": "https://media.shelf.example/p.webp"}, "image_link"),
        ({"brand": ""}, "brand"),
        ({"fb_product_category": 999999}, "fb_product_category"),
        ({"pattern": "p" * 101}, "pattern"),
    ],
)
def test_invalid_items_are_rejected(kw: dict[str, Any], field: str) -> None:
    with pytest.raises(FeedInvalidError) as exc:
        build_feed_csv([item(**kw)])
    assert field in {i.field for i in exc.value.issues}


def test_duplicate_ids_are_rejected() -> None:
    with pytest.raises(FeedInvalidError, match="duplicate"):
        build_feed_csv([item(), item()])


def test_long_titles_only_warn() -> None:
    _, warnings = build_feed_csv([item(title="Blue cotton saree " * 5)])
    assert [w.field for w in warnings] == ["title"]


def test_clean_text_strips_links_contacts_and_html() -> None:
    raw = "<p>Lovely saree!</p> Call 98765 43210 or mail a@b.co, see https://x.y/z or shop.com"
    cleaned = clean_text(raw)
    assert cleaned.startswith("Lovely saree! Call or mail")
    for leaked in ("<", "98765", "43210", "@", "http", "x.y", "shop.com"):
        assert leaked not in cleaned
    assert clean_text("word " * 50, max_len=20).endswith("…")


@pytest.mark.parametrize(
    ("raw", "digits"),
    [
        ("98765 43210", "919876543210"),
        ("+91 98765-43210", "919876543210"),
        ("09876543210", "919876543210"),
        ("0091 98765 43210", "919876543210"),
        ("(+44) 7700 900123", "447700900123"),
    ],
)
def test_normalise_whatsapp_number(raw: str, digits: str) -> None:
    assert normalise_number(raw) == digits


@pytest.mark.parametrize("raw", ["12345", "5876543210", "+91 98765"])
def test_bad_numbers_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidWhatsAppNumberError):
        normalise_number(raw)


def test_order_link_prefills_message() -> None:
    message = order_message("Sharma Sarees", "Blue cotton saree", 120000,
                            "https://shelf.example/s/sharma/p/1", lang="hi")  # fmt: skip
    link = order_link("98765 43210", message)
    parts = urlsplit(link)
    assert parts.scheme == "https"
    assert parts.netloc == "wa.me"
    assert parts.path == "/919876543210"
    text = parse_qs(parts.query)["text"][0]
    assert text == message
    assert "₹1,200" in text
    assert " " not in link and "&" not in parts.query.replace("text=", "")


def test_feed_problems_do_not_block_the_shop_page(tmp_path: Any) -> None:
    from pathlib import Path

    from PIL import Image

    from engine.export.provenance import save_jpeg
    from engine.pipeline.publish import ShopInfo, publish
    from engine.pipeline.schemas import DetectedProduct, Enriched, FinalImage, PriceDecision

    img = Path(tmp_path) / "p.jpg"
    img.write_bytes(save_jpeg(Image.new("RGB", (600, 600), "white"), ai_background=False))
    shop = ShopInfo(
        name="Shop",
        slug="shop",
        whatsapp="98765 43210",
        public_base_url="http://localhost:5173",
        media_base_url="http://localhost:8000/m",
    )
    result = publish(
        shop,
        [
            DetectedProduct(
                idx=1,
                description="x",
                colour="red",
                noun="item",
                first_seen_s=0,
                last_seen_s=1,
                best_frame_s=0,
            )
        ],
        [PriceDecision(product_idx=1, price_inr=100, source="seller", confidence=1)],
        [
            Enriched(
                product_idx=1,
                title_en="Red cup",
                title_hi="लाल कप",
                description_en="A cup.",
                description_hi="कप।",
                category="home_decor",
                colour="red",
                material=None,
                pattern=None,
            )
        ],
        [FinalImage(product_idx=1, path=img, ai_background=False)],
        Path(tmp_path) / "out",
    )
    assert result.published == 1  # the shop page has the item
    assert result.feed_csv is None  # but Meta would reject http links
    assert {i.field for i in result.feed_errors} == {"link", "image_link"}


def test_shop_items_feed_links_sold_out_and_credit(tmp_path: Any) -> None:
    from pathlib import Path

    from PIL import Image

    from engine.export.provenance import save_jpeg
    from engine.pipeline.publish import ShopInfo, ShopItem, publish_items

    img = Path(tmp_path) / "p.jpg"
    img.write_bytes(save_jpeg(Image.new("RGB", (600, 600), "white"), ai_background=False))
    shop = ShopInfo(
        name="Gupta Store",
        slug="gupta",
        whatsapp="98765 43210",
        public_base_url="https://shop.example",
        media_base_url="https://shop.example/api/v1/public/media/gupta/v3",
    )
    items = [
        ShopItem(id="gupta-a1", title_en="Pepsi 750 ml", title_hi="पेप्सी", price_inr=40,
                 image=img, category="soda", brand="Pepsi"),
        ShopItem(id="gupta-b2", title_en="Mirinda can", title_hi="मिरिंडा", price_inr=35,
                 image=img, sold_out=True, category="other",
                 image_credit="Open Food Facts", image_credit_url="https://world.openfoodfacts.org/product/1"),
        ShopItem(id="gupta-c3", title_en="Bread", title_hi="ब्रेड", price_inr=0, image=img),
    ]  # fmt: skip
    result = publish_items(shop, items, Path(tmp_path) / "out")
    assert result.published == 2
    assert result.skipped == [("gupta-c3", "no price")]
    assert result.feed_csv is not None
    rows = {r["id"]: r for r in csv.DictReader(io.StringIO(result.feed_csv.read_text("utf-8")))}
    # The photo URL is the media base plus the file: exactly what the public media route serves.
    assert rows["gupta-a1"]["image_link"] == (
        "https://shop.example/api/v1/public/media/gupta/v3/gupta-a1.jpg"
    )
    assert rows["gupta-a1"]["availability"] == "in stock"
    assert rows["gupta-b2"]["availability"] == "out of stock"
    assert rows["gupta-b2"]["fb_product_category"] == ""
    assert any(w.field == "fb_product_category" for w in result.feed_warnings)
    catalog = json.loads(result.catalog_json.read_text(encoding="utf-8"))
    sold = next(p for p in catalog["products"] if p["id"] == "gupta-b2")
    assert sold["sold_out"] is True
    assert sold["image_credit"] == "Open Food Facts"
