"""Pack photos of branded goods from Open Food Facts (images under CC BY-SA 3.0).

Docs: openfoodfacts.github.io/openfoodfacts-server/api/ (product by barcode, image layout, rate
limits) and search.openfoodfacts.org/openapi.json (search). Only three fixed hosts are reachable;
the server builds every URL itself from a barcode, never from a URL sent by the browser.
"""

from __future__ import annotations

import re
import time
from typing import Any

import httpx
from pydantic import BaseModel

from engine.net import AllowlistTransport

SEARCH_URL = "https://search.openfoodfacts.org/search"
PRODUCT_URL = "https://world.openfoodfacts.org/api/v2/product/{code}.json"
PAGE_URL = "https://world.openfoodfacts.org/product/{code}"
HOSTS = ("search.openfoodfacts.org", "world.openfoodfacts.org", "images.openfoodfacts.org")
IMAGE_HOST = "images.openfoodfacts.org"
CREDIT = "Open Food Facts contributors, CC BY-SA 3.0"
FIELDS = "code,product_name,brands,image_front_url,countries_tags"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
# Their limit is 10 searches a minute per IP; stay under it for the whole server.
SEARCHES_PER_MINUTE = 8

_BARCODE = re.compile(r"^\d{8,14}$")
# Selected images: /images/products/<folders>/<name>.<rev>.<100|200|400|full>.jpg
_IMAGE_PATH = re.compile(r"^/images/products/[0-9/]+/[a-z0-9_]+\.\d+\.(?:100|200|400|full)\.jpg$")
_WORD = re.compile(r"[a-z0-9]+")
_OPERATORS = frozenset({"AND", "OR", "NOT", "TO"})


class SearchBusyError(Exception):
    pass


class PackPhoto(BaseModel):
    code: str
    name: str
    brand: str | None
    image_url: str  # 400 px front image, shown as the choice
    india: bool

    @property
    def page_url(self) -> str:
        return PAGE_URL.format(code=self.code)


def valid_barcode(code: str) -> bool:
    return bool(_BARCODE.match(code))


def image_url_ok(url: str) -> bool:
    parsed = httpx.URL(url)
    return (
        parsed.scheme == "https"
        and parsed.host == IMAGE_HOST
        and bool(_IMAGE_PATH.match(parsed.path))
    )


def thumb_size(url: str) -> str:
    """The documented 200 px version, for the picker grid."""
    return re.sub(r"\.(?:100|400|full)\.jpg$", ".200.jpg", url)


def full_size(url: str) -> str:
    """The documented full-size name of a selected image (`front_en.4.400.jpg` -> `.full.jpg`)."""
    return re.sub(r"\.(?:100|200|400)\.jpg$", ".full.jpg", url)


def clean_query(text: str) -> str:
    """Plain words only: nothing that the search service would read as query syntax."""
    words = [w for w in re.findall(r"[A-Za-z0-9]+", text) if w not in _OPERATORS]
    return " ".join(words)[:80]


def _words(text: str) -> set[str]:
    return {w.removesuffix("s") for w in _WORD.findall(text.lower()) if len(w) > 1}


def _photo(hit: dict[str, Any]) -> PackPhoto | None:
    code, url = str(hit.get("code") or ""), hit.get("image_front_url")
    if not valid_barcode(code) or not isinstance(url, str) or not image_url_ok(url):
        return None
    brands = hit.get("brands")
    brand = ", ".join(brands[:2]) if isinstance(brands, list) else brands
    return PackPhoto(
        code=code,
        name=str(hit.get("product_name") or brand or code)[:120],
        brand=str(brand)[:80] if brand else None,
        image_url=url,
        india="en:india" in (hit.get("countries_tags") or []),
    )


def rank(query: str, photos: list[PackPhoto], limit: int = 8) -> list[PackPhoto]:
    """Words shared with the product name count double (the brand alone matches every product the
    brand makes); Indian products first on ties."""
    want = _words(query)
    scored = {}
    for p in photos:
        name = want & _words(p.name)
        brand = (want & _words(p.brand or "")) - name
        scored[p.code] = (2 * len(name) + len(brand), p.india, p)
    best = sorted(scored.values(), key=lambda s: (s[0], s[1]), reverse=True)
    return [p for score, _, p in best if score > 0][:limit]


class OpenFoodFacts:
    def __init__(self, user_agent: str, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self.client = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=httpx.Timeout(15.0, connect=10.0),
            transport=AllowlistTransport(HOSTS, inner=inner),
            follow_redirects=False,
        )
        self._cache: dict[str, tuple[float, list[PackPhoto]]] = {}
        self._recent: list[float] = []

    async def aclose(self) -> None:
        await self.client.aclose()

    def _take_search_slot(self) -> None:
        now = time.monotonic()
        self._recent = [t for t in self._recent if now - t < 60]
        if len(self._recent) >= SEARCHES_PER_MINUTE:
            raise SearchBusyError
        self._recent.append(now)

    async def _search_once(self, q: str) -> list[PackPhoto]:
        self._take_search_slot()
        r = await self.client.get(SEARCH_URL, params={"q": q, "page_size": 24, "fields": FIELDS})
        r.raise_for_status()
        hits = r.json().get("hits") or []
        return [p for p in (_photo(h) for h in hits if isinstance(h, dict)) if p is not None]

    async def search(self, text: str) -> list[PackPhoto]:
        query = clean_query(text)
        if not query:
            return []
        cached = self._cache.get(query.lower())
        if cached and time.monotonic() - cached[0] < 3600:
            return cached[1]
        found = await self._search_once(query)
        # Their full-text ranking is loose; a brand-word search limited to India finds packs
        # the phrase search misses (e.g. "Haldiram ...").
        first = query.split()[0].capitalize()
        found += await self._search_once(f'{first} AND countries_tags:"en:india"')
        result = rank(query, found)
        if len(self._cache) > 200:
            self._cache.clear()
        self._cache[query.lower()] = (time.monotonic(), result)
        return result

    async def by_barcode(self, code: str) -> PackPhoto | None:
        if not valid_barcode(code):
            return None
        r = await self.client.get(PRODUCT_URL.format(code=code), params={"fields": FIELDS})
        if r.status_code == 404:
            return None
        r.raise_for_status()
        product = r.json().get("product")
        return _photo({**product, "code": code}) if isinstance(product, dict) else None

    async def image(self, photo: PackPhoto) -> bytes:
        """The full-size front image (falls back to the 400 px one)."""
        for url in (full_size(photo.image_url), photo.image_url):
            if not image_url_ok(url):
                continue
            async with self.client.stream("GET", url) as r:
                if r.status_code != 200:
                    continue
                data = bytearray()
                async for chunk in r.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_IMAGE_BYTES:
                        break
                else:
                    return bytes(data)
        raise httpx.HTTPError("no usable image")
