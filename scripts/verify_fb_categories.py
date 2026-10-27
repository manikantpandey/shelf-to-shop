"""Check our fb_product_category mapping against Meta's published taxonomy.

Run: uv run python scripts/verify_fb_categories.py
Exits non-zero if any id is missing or its published name changed.
"""

from __future__ import annotations

import csv
import io
import sys

import httpx

from engine.export.categories import FB_CATEGORIES

URL = "https://www.facebook.com/products/categories/en_US.txt"


def main() -> int:
    response = httpx.get(URL, timeout=30, follow_redirects=False)
    response.raise_for_status()
    rows = csv.reader(io.StringIO(response.text.lstrip("﻿")))
    next(rows)  # header: category_id,category
    published = {int(cid): name for cid, name in rows}
    problems = [
        f"{key}: id {cid} {'missing' if cid not in published else f'now {published[cid]!r}'}"
        for key, (cid, name) in FB_CATEGORIES.items()
        if published.get(cid) != name
    ]
    for line in problems:
        print(line)
    print(f"{len(FB_CATEGORIES) - len(problems)}/{len(FB_CATEGORIES)} mappings match "
          f"({len(published)} published categories)")  # fmt: skip
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
