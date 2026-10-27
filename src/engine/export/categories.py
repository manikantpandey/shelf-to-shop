"""Our product categories mapped to Meta's `fb_product_category` taxonomy.

Every id and name below was checked against Meta's published list
https://www.facebook.com/products/categories/en_US.txt on 2026-10-27; re-check with
`uv run python scripts/verify_fb_categories.py`. Meta has no saree-specific category, so sarees
use the closest exact match (women's clothing).
"""

from __future__ import annotations

from typing import Literal

CategoryKey = Literal[
    "saree",
    "womens_clothing",
    "mens_clothing",
    "scarf_dupatta",
    "womens_sandals",
    "womens_slippers",
    "womens_flats",
    "womens_shoes",
    "mens_sandals",
    "mens_shoes",
    "mens_footwear",
    "kids_shoes",
    "footwear",
    "bracelets_bangles",
    "home_decor",
    "decorative_accents",
    "baskets",
    "arts_crafts",
    "spices",
    "snacks",
    "grains",
    "tea_coffee",
    "dairy",
    "food",
    "other",
]

# key -> (fb_product_category id, name as published)
FB_CATEGORIES: dict[str, tuple[int, str]] = {
    "saree": (455, "clothing & accessories > clothing > women's clothing"),
    "womens_clothing": (455, "clothing & accessories > clothing > women's clothing"),
    "mens_clothing": (472, "clothing & accessories > clothing > men's clothing"),
    "scarf_dupatta": (
        381,
        "clothing & accessories > clothing accessories > women's accessories > scarves & wraps",
    ),
    "womens_sandals": (412, "clothing & accessories > shoes & footwear > women's shoes > sandals"),
    "womens_slippers": (
        411,
        "clothing & accessories > shoes & footwear > women's shoes > slippers",
    ),
    "womens_flats": (413, "clothing & accessories > shoes & footwear > women's shoes > flats"),
    "womens_shoes": (415, "clothing & accessories > shoes & footwear > women's shoes"),
    "mens_sandals": (416, "clothing & accessories > shoes & footwear > men's shoes > sandals"),
    "mens_shoes": (
        417,
        "clothing & accessories > shoes & footwear > men's shoes > casual & dress shoes",
    ),
    "mens_footwear": (422, "clothing & accessories > shoes & footwear > men's shoes"),
    "kids_shoes": (427, "clothing & accessories > shoes & footwear > kids' shoes"),
    "footwear": (429, "clothing & accessories > shoes & footwear"),
    "bracelets_bangles": (327, "jewelry & watches > jewelry > bracelets"),
    "home_decor": (375, "home > home goods > home decor"),
    "decorative_accents": (374, "home > home goods > home decor > decorative accents"),
    "baskets": (973, "home > home goods > home decor > decorative accents > baskets"),
    "arts_crafts": (169, "arts & crafts"),
    "spices": (5, "food & beverages > food > spices & seasonings"),
    "snacks": (3, "food & beverages > food > snacks & chips"),
    "grains": (6, "food & beverages > food > pasta & grains"),
    "tea_coffee": (24, "food & beverages > beverages > coffee & tea"),
    "dairy": (13, "food & beverages > food > dairy, eggs & cheese"),
    "food": (18, "food & beverages > food"),
}

# Apparel categories where Meta asks for colour/material/pattern (and gender/age group).
APPAREL = frozenset(
    {"saree", "womens_clothing", "mens_clothing", "scarf_dupatta", "womens_sandals",
     "womens_slippers", "womens_flats", "womens_shoes", "mens_sandals", "mens_shoes",
     "mens_footwear", "kids_shoes", "footwear"}
)  # fmt: skip


def fb_category_id(key: str) -> int | None:
    entry = FB_CATEGORIES.get(key)
    return entry[0] if entry else None
