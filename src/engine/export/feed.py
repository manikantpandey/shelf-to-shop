"""Meta catalog feed CSV (developers.facebook.com/docs/marketing-api/catalog/reference).

Required columns: id, title, description, availability, condition, price, link, image_link, brand,
and fb_product_category (or google_product_category). Apparel adds color, material and pattern.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Literal

from pydantic import BaseModel, Field

from engine.export.categories import FB_CATEGORIES
from engine.export.text import is_shouting
from engine.prices.inr import feed_price

FEED_COLUMNS = [
    "id",
    "title",
    "description",
    "availability",
    "condition",
    "price",
    "link",
    "image_link",
    "brand",
    "fb_product_category",
    "color",
    "material",
    "pattern",
    "additional_image_link",
]
_ID = re.compile(r"^[A-Za-z0-9_\-]{1,100}$")
_HTML = re.compile(r"<[^>]+>")
_LINKY = re.compile(r"(?i)https?://|www\.")
_IMAGE = re.compile(r"(?i)\.(jpe?g|png)(\?.*)?$")
_VALID_CATEGORY_IDS = frozenset(cid for cid, _ in FB_CATEGORIES.values())


class FeedItem(BaseModel):
    id: str
    title: str
    description: str
    price_paise: int
    link: str
    image_link: str
    brand: str
    fb_product_category: int
    availability: Literal["in stock", "out of stock"] = "in stock"
    condition: Literal["new", "refurbished", "used"] = "new"
    color: str | None = None
    material: str | None = None
    pattern: str | None = None
    additional_image_links: list[str] = Field(default_factory=list)


class FeedIssue(BaseModel):
    item_id: str
    field: str
    severity: Literal["error", "warning"]
    message: str


class FeedInvalidError(ValueError):
    def __init__(self, issues: list[FeedIssue]) -> None:
        super().__init__(f"{len(issues)} feed problem(s): " + "; ".join(i.message for i in issues))
        self.issues = issues


def _url_ok(url: str) -> bool:
    return url.startswith("https://") and len(url) <= 2000 and " " not in url


def validate_item(item: FeedItem) -> list[FeedIssue]:
    issues: list[FeedIssue] = []

    def err(field: str, message: str) -> None:
        issues.append(FeedIssue(item_id=item.id, field=field, severity="error", message=message))

    def warn(field: str, message: str) -> None:
        issues.append(FeedIssue(item_id=item.id, field=field, severity="warning", message=message))

    if not _ID.match(item.id):
        err("id", "id must be 1-100 letters, digits, '-' or '_'")
    if not item.title.strip() or len(item.title) > 200:
        err("title", "title must be 1-200 characters")
    elif len(item.title) > 65:
        warn("title", "titles over 65 characters get cut off")
    desc = item.description
    if not desc.strip() or len(desc) > 9999:
        err("description", "description must be 1-9999 characters")
    if _HTML.search(desc):
        err("description", "description must be plain text, not HTML")
    if _LINKY.search(desc):
        err("description", "description must not contain links")
    if is_shouting(desc):
        err("description", "description must not be all capital letters")
    if item.price_paise <= 0:
        err("price", "price must be more than zero")
    if not _url_ok(item.link):
        err("link", "link must be a valid https URL")
    if not _url_ok(item.image_link) or not _IMAGE.search(item.image_link):
        err("image_link", "image_link must be an https URL to a JPEG or PNG")
    if not item.brand.strip() or len(item.brand) > 100:
        err("brand", "brand must be 1-100 characters")
    if item.fb_product_category not in _VALID_CATEGORY_IDS:
        err("fb_product_category", "fb_product_category is not one of our verified categories")
    for field, limit in (("color", 200), ("material", 200), ("pattern", 100)):
        value = getattr(item, field)
        if value is not None and len(value) > limit:
            err(field, f"{field} must be at most {limit} characters")
    if len(item.additional_image_links) > 50:
        err("additional_image_link", "at most 50 additional images")
    if any(not _url_ok(u) for u in item.additional_image_links):
        err("additional_image_link", "additional images must be https URLs")
    return issues


def build_feed_csv(items: list[FeedItem]) -> tuple[str, list[FeedIssue]]:
    """CSV text with a header row. Raises FeedInvalidError on any error; returns warnings."""
    issues = [issue for item in items for issue in validate_item(item)]
    seen: set[str] = set()
    for item in items:
        if item.id in seen:
            issues.append(FeedIssue(item_id=item.id, field="id", severity="error",
                                    message=f"duplicate id {item.id}"))  # fmt: skip
        seen.add(item.id)
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        raise FeedInvalidError(errors)

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(FEED_COLUMNS)
    for item in items:
        writer.writerow(
            [
                item.id,
                item.title,
                item.description,
                item.availability,
                item.condition,
                feed_price(item.price_paise),
                item.link,
                item.image_link,
                item.brand,
                str(item.fb_product_category),
                item.color or "",
                item.material or "",
                item.pattern or "",
                ",".join(item.additional_image_links),
            ]
        )
    return buf.getvalue(), [i for i in issues if i.severity == "warning"]
