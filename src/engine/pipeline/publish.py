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

from engine.export.categories import fb_category_id
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


class ShopItem(BaseModel):
    """One approved item, from any video. `id` is the retailer id: stable across republishes."""

    id: str
    title_en: str
    title_hi: str
    description_en: str = ""
    description_hi: str = ""
    price_inr: int
    image: Path
    ai_background: bool = False
    sold_out: bool = False
    category: str = "other"
    colour: str = ""
    brand: str | None = None
    material: str | None = None
    pattern: str | None = None
    # Set when the photo is not the seller's own (e.g. Open Food Facts, CC BY-SA).
    image_credit: str | None = None
    image_credit_url: str | None = None
    # Printed price; when above price_inr the shop shows it struck through and the feed has a sale.
    mrp_inr: int | None = None
    section: str | None = None
    featured: bool = False


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
    sold_out: bool
    image_credit: str | None
    image_credit_url: str | None
    mrp_display: str | None
    section: str | None
    featured: bool
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
    # (retailer id, reason) for items that could not go on the shop page at all.
    skipped: list[tuple[str, str]]
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
    """Publish one pipeline run (the CLI path): items are keyed by their index in the video."""
    price = {d.product_idx: d.price_inr for d in decisions}
    text = {e.product_idx: e for e in enriched}
    image = {i.product_idx: i for i in images}
    items: list[ShopItem] = []
    skipped: list[tuple[str, str]] = []
    for p in products:
        rid = retailer_id(shop.slug, p.idx)
        value, e, img = price.get(p.idx), text.get(p.idx), image.get(p.idx)
        if value is None:
            skipped.append((rid, "no price"))
        elif img is None:
            skipped.append((rid, "no photo"))
        elif e is None:
            skipped.append((rid, "no title"))
        else:
            items.append(
                ShopItem(
                    id=rid,
                    title_en=e.title_en,
                    title_hi=e.title_hi,
                    description_en=e.description_en,
                    description_hi=e.description_hi,
                    price_inr=value,
                    image=img.path,
                    ai_background=img.ai_background,
                    category=e.category,
                    colour=e.colour,
                    brand=e.brand,
                    material=e.material,
                    pattern=e.pattern,
                )
            )
    result = publish_items(shop, items, out_dir)
    return result.model_copy(update={"skipped": skipped + result.skipped})


def publish_items(shop: ShopInfo, items: list[ShopItem], out_dir: Path) -> PublishResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    img_dir = out_dir / "images"
    img_dir.mkdir(exist_ok=True)
    number = normalise_number(shop.whatsapp)
    base = shop.public_base_url.rstrip("/")
    media = shop.media_base_url.rstrip("/")

    catalog: list[CatalogProduct] = []
    feed: list[FeedItem] = []
    skipped: list[tuple[str, str]] = []
    for it in items:
        if it.price_inr <= 0:
            skipped.append((it.id, "no price"))
            continue
        if not it.image.is_file():
            skipped.append((it.id, "no photo"))
            continue
        paise = rupees_to_paise(it.price_inr)
        mrp = rupees_to_paise(it.mrp_inr) if it.mrp_inr and it.mrp_inr > it.price_inr else None
        url = f"{base}/s/{shop.slug}/p/{it.id}"
        file_name = f"{it.id}.jpg"
        shutil.copyfile(it.image, img_dir / file_name)
        catalog.append(
            CatalogProduct(
                id=it.id,
                title_en=it.title_en,
                title_hi=it.title_hi,
                description_en=it.description_en,
                description_hi=it.description_hi,
                price_paise=paise,
                price_display=format_inr(paise),
                image=file_name,
                ai_background=it.ai_background,
                sold_out=it.sold_out,
                image_credit=it.image_credit,
                image_credit_url=it.image_credit_url,
                mrp_display=format_inr(mrp) if mrp else None,
                section=it.section,
                featured=it.featured,
                colour=it.colour,
                material=it.material,
                pattern=it.pattern,
                order_link_en=order_link(
                    number, order_message(shop.name, it.title_en, paise, url, "en")
                ),
                order_link_hi=order_link(
                    number, order_message(shop.name, it.title_hi, paise, url, "hi")
                ),
            )
        )
        feed.append(
            FeedItem(
                id=it.id,
                title=it.title_en,
                description=it.description_en or it.title_en,
                availability="out of stock" if it.sold_out else "in stock",
                price_paise=mrp or paise,
                sale_price_paise=paise if mrp else None,
                link=url,
                image_link=f"{media}/{file_name}",
                # The maker's brand when printed on the pack (Haldiram's, Pepsi), else the shop.
                brand=it.brand or shop.brand or shop.name,
                fb_product_category=fb_category_id(it.category),
                color=it.colour or None,
                material=it.material,
                pattern=it.pattern,
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
