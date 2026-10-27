"""Build the shareable outputs from a reviewed run: catalog JSON, Meta feed CSV, image zip.

The catalog JSON is what the public shop page shows, so it holds approved public fields only:
no internal ids, no seller email, no raw video or audio.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from pydantic import BaseModel

from engine.export.categories import FB_CATEGORIES
from engine.export.feed import FeedIssue, FeedItem, build_feed_csv, validate_item
from engine.export.whatsapp import normalise_number, order_link, order_message
from engine.pipeline.schemas import DetectedProduct, Enriched, FinalImage, PriceDecision
from engine.prices.inr import format_inr, rupees_to_paise


class ShopInfo(BaseModel):
    name: str
    slug: str
    whatsapp: str
    public_base_url: str  # where /s/<slug> pages are served
    media_base_url: str  # where approved product images are served
    brand: str | None = None


class CatalogProduct(BaseModel):
    id: str
    title_en: str
    title_hi: str
    description_en: str
    description_hi: str
    price_paise: int
    price_display: str
    image: str
    ai_background: bool
    colour: str
    material: str | None
    pattern: str | None
    order_link_en: str
    order_link_hi: str


class Catalog(BaseModel):
    shop: dict[str, str]
    products: list[CatalogProduct]


class PublishResult(BaseModel):
    catalog_json: Path
    # None when no item can go into the Meta feed (e.g. the site is not on https yet).
    feed_csv: Path | None
    images_zip: Path
    published: int
    skipped: list[tuple[int, str]]
    feed_warnings: list[FeedIssue]
    # Items left out of the feed only; they are still on the shop page.
    feed_errors: list[FeedIssue]


def retailer_id(slug: str, idx: int) -> str:
    return f"{slug}-{idx:02d}"


def publish(
    shop: ShopInfo,
    products: list[DetectedProduct],
    decisions: list[PriceDecision],
    enriched: list[Enriched],
    images: list[FinalImage],
    out_dir: Path,
) -> PublishResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    img_dir = out_dir / "images"
    img_dir.mkdir(exist_ok=True)
    price = {d.product_idx: d.price_inr for d in decisions}
    text = {e.product_idx: e for e in enriched}
    image = {i.product_idx: i for i in images}
    number = normalise_number(shop.whatsapp)
    base = shop.public_base_url.rstrip("/")
    media = shop.media_base_url.rstrip("/")

    catalog: list[CatalogProduct] = []
    feed: list[FeedItem] = []
    skipped: list[tuple[int, str]] = []
    for p in products:
        if price.get(p.idx) is None:
            skipped.append((p.idx, "no price"))
            continue
        if p.idx not in image:
            skipped.append((p.idx, "no photo"))
            continue
        e = text.get(p.idx)
        if e is None:
            skipped.append((p.idx, "no title"))
            continue
        rid = retailer_id(shop.slug, p.idx)
        paise = rupees_to_paise(int(price[p.idx] or 0))
        url = f"{base}/s/{shop.slug}/p/{rid}"
        file_name = f"{rid}.jpg"
        shutil.copyfile(image[p.idx].path, img_dir / file_name)
        catalog.append(
            CatalogProduct(
                id=rid,
                title_en=e.title_en,
                title_hi=e.title_hi,
                description_en=e.description_en,
                description_hi=e.description_hi,
                price_paise=paise,
                price_display=format_inr(paise),
                image=file_name,
                ai_background=image[p.idx].ai_background,
                colour=e.colour,
                material=e.material,
                pattern=e.pattern,
                order_link_en=order_link(
                    number, order_message(shop.name, e.title_en, paise, url, "en")
                ),
                order_link_hi=order_link(
                    number, order_message(shop.name, e.title_hi, paise, url, "hi")
                ),
            )
        )
        feed.append(
            FeedItem(
                id=rid,
                title=e.title_en,
                description=e.description_en or e.title_en,
                price_paise=paise,
                link=url,
                image_link=f"{media}/{shop.slug}/{file_name}",
                # The maker's brand when printed on the pack (Haldiram's, Pepsi), else the shop.
                brand=e.brand or shop.brand or shop.name,
                fb_product_category=FB_CATEGORIES[e.category][0],
                color=e.colour or None,
                material=e.material,
                pattern=e.pattern,
            )
        )

    # The shop page never depends on the Meta feed: items Meta would reject are left out of the
    # feed (with the reason) but stay in the catalog.
    feed_errors: list[FeedIssue] = []
    feed_ok: list[FeedItem] = []
    for entry in feed:
        errors = [i for i in validate_item(entry) if i.severity == "error"]
        feed_errors.extend(errors)
        if not errors:
            feed_ok.append(entry)
    feed_path: Path | None = None
    warnings: list[FeedIssue] = []
    if feed_ok:
        csv_text, warnings = build_feed_csv(feed_ok)
        feed_path = out_dir / "meta_catalog_feed.csv"
        feed_path.write_text(csv_text, encoding="utf-8")
    catalog_path = out_dir / "catalog.json"
    doc = Catalog(shop={"name": shop.name, "slug": shop.slug, "whatsapp": number},
                  products=catalog)  # fmt: skip
    catalog_path.write_text(
        json.dumps(doc.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    zip_path = out_dir / f"{shop.slug}_photos.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
        for item in catalog:
            zf.write(img_dir / item.image, arcname=item.image)
    return PublishResult(
        catalog_json=catalog_path,
        feed_csv=feed_path,
        images_zip=zip_path,
        published=len(catalog),
        skipped=skipped,
        feed_warnings=warnings,
        feed_errors=feed_errors,
    )
