"""Titles, descriptions (English and Hindi) and catalog attributes for each product."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel, Field

from engine.agents.structured import untrusted
from engine.export.categories import FB_CATEGORIES
from engine.export.text import clean_text
from engine.media.composite import mask_bbox
from engine.media.masks import load_mask
from engine.pipeline.schemas import Cutout, DetectedProduct, Enriched
from engine.providers.interfaces import StructuredLLM
from engine.runlog import CallContext

CategoryKey = Literal[tuple(FB_CATEGORIES)]  # type: ignore[valid-type]


class EnrichItem(BaseModel):
    idx: int
    title_en: str = Field(description="buyer-facing title, max 60 characters, no price")
    title_hi: str = Field(description="the same title in natural Hindi (Devanagari)")
    description_en: str = Field(description="1-2 plain sentences about what is visible")
    description_hi: str = Field(description="the same description in natural Hindi")
    brand: str | None = Field(description="brand printed on the pack or label, else null")
    category: CategoryKey  # type: ignore[valid-type]
    colour: str
    material: str | None = Field(description="only if visible or stated, else null")
    pattern: str | None = Field(description="print or weave if any, else null")


class EnrichBatch(BaseModel):
    items: list[EnrichItem]


TASK = (
    "Write catalog entries for a small Indian shop. For each item give a short title a buyer "
    "would search for (for example 'Blue cotton saree with gold border'), the same title in "
    "natural Hindi, and one or two plain sentences describing only what is visible. Never "
    "mention prices, discounts, phone numbers, links or claims you cannot see (no 'best "
    "quality', no 'pure silk' unless it is clear). Give the brand only if it is printed on the "
    "item. When an item's tag_text is a sign naming the product (for example 'MADHUR SUGAR 5KG "
    "@ 225/-'), use that product name, brand and pack size in the title instead of describing "
    "the packaging ('Madhur sugar 5 kg', not 'White sacks on a pallet'). "
    "Choose the closest category from the list. "
    "Use the item photos in the order given."
)


def _crop_data_url(frame: Path, mask_path: Path, max_side: int = 384) -> str:
    img = Image.open(frame).convert("RGB")
    x1, y1, x2, y2 = mask_bbox(load_mask(mask_path))
    crop = img.crop((x1, y1, x2, y2))
    crop.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    crop.save(buf, "JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


async def enrich(
    ctx: CallContext,
    llm: StructuredLLM,
    products: list[DetectedProduct],
    cutouts: list[Cutout],
) -> list[Enriched]:
    by_idx = {c.product_idx: c for c in cutouts}
    listing = [
        {
            "idx": p.idx,
            "description": p.description,
            "colour": p.colour,
            "noun": p.noun,
            "tag_text": p.tag_text,
        }
        for p in products
    ]
    content: list[dict[str, str]] = [
        {"type": "input_text", "text": TASK + "\n" + untrusted("products", listing)}
    ]
    for p in products:
        cut = by_idx.get(p.idx)
        if cut is None:
            continue
        content.append({"type": "input_text", "text": f"Photo of item {p.idx}:"})
        content.append({"type": "input_image", "image_url": _crop_data_url(cut.frame, cut.mask)})

    result = await llm.run(
        ctx,
        output=EnrichBatch,
        instructions="You write short, honest product listings.",
        content=content,
        estimate_input_tokens=1000 + 900 * len(products),
        effort="minimal",
        max_output_tokens=600 * max(1, len(products)),
        inputs_summary={"products": len(products)},
    )
    wanted = {p.idx for p in products}
    out: list[Enriched] = []
    for item in result.value.items:
        if item.idx not in wanted:
            continue  # ignore anything the model invented
        wanted.discard(item.idx)
        out.append(
            Enriched(
                product_idx=item.idx,
                title_en=clean_text(item.title_en, 65) or f"Item {item.idx}",
                title_hi=clean_text(item.title_hi, 65) or clean_text(item.title_en, 65),
                description_en=clean_text(item.description_en, 500),
                description_hi=clean_text(item.description_hi, 500),
                brand=clean_text(item.brand, 100) if item.brand else None,
                category=item.category,
                colour=clean_text(item.colour, 60),
                material=clean_text(item.material, 60) if item.material else None,
                pattern=clean_text(item.pattern, 60) if item.pattern else None,
            )
        )
    for idx in sorted(wanted):  # the model skipped an item: fall back to the detection text
        p = next(x for x in products if x.idx == idx)
        title = clean_text(p.description, 65) or f"Item {idx}"
        out.append(Enriched(product_idx=idx, title_en=title, title_hi=title,
                            description_en=title, description_hi=title, category="womens_clothing"
                            if p.noun == "saree" else "arts_crafts", colour=p.colour,
                            material=None, pattern=None))  # fmt: skip
    return sorted(out, key=lambda e: e.product_idx)
