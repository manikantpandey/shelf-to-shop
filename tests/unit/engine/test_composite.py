from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from engine.export.provenance import COMPOSITE_SYNTHETIC, PHOTO_ORIGINAL, save_jpeg
from engine.media.composite import (
    EXPORT_SIZE,
    add_corner_mark,
    compose,
    fill_holes,
    mask_bbox,
)


def _photo(w: int = 640, h: int = 360, seed: int = 1) -> Image.Image:
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(0, 255, (h, w, 3), dtype=np.uint8))


def _mask(w: int = 640, h: int = 360) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    return ((xx - 300) / 180) ** 2 + ((yy - 190) / 110) ** 2 <= 1


def test_product_pixels_are_copied_exactly_before_resize() -> None:
    photo, mask = _photo(), _mask()
    backdrop = Image.new("RGB", (900, 900), (200, 200, 205))
    result = compose(photo, mask, backdrop, padding=0.0)
    assert result.product_pixels_exact
    assert result.image.size == (EXPORT_SIZE, EXPORT_SIZE)


def test_shadow_never_touches_product_pixels() -> None:
    # Product box exactly EXPORT_SIZE wide and no padding: no final resize, compare directly.
    w, h = 1200, 800
    photo = _photo(w, h, seed=3)
    mask = np.zeros((h, w), dtype=bool)
    mask[100:700, 88 : 88 + EXPORT_SIZE] = True
    mask[100:160, 88:200] = False  # notched corners: not a plain rectangle
    mask[640:700, 1000:1112] = False
    x1, y1, x2, y2 = mask_bbox(mask)
    assert x2 - x1 == EXPORT_SIZE
    result = compose(photo, mask, Image.new("RGB", (100, 100), "white"), padding=0.0)
    out, src = np.asarray(result.image), np.asarray(photo)
    ox = round((x1 + x2) / 2 - EXPORT_SIZE / 2)
    oy = round((y1 + y2) / 2 - EXPORT_SIZE / 2)
    ys, xs = np.nonzero(mask)
    assert np.array_equal(out[ys - oy, xs - ox], src[ys, xs])
    outside = np.ones(out.shape[:2], dtype=bool)
    outside[ys - oy, xs - ox] = False
    assert out[outside].min() < 250  # the white backdrop got a contact shadow


def test_small_products_are_upscaled_to_feed_size() -> None:
    photo = _photo(200, 120)
    mask = np.zeros((120, 200), dtype=bool)
    mask[30:90, 50:150] = True
    result = compose(photo, mask, Image.new("RGB", (64, 64), "grey"))
    assert result.upscaled
    assert min(result.image.size) >= 500


def test_fill_holes_closes_enclosed_gaps_only() -> None:
    mask = np.zeros((200, 300), dtype=bool)
    mask[40:160, 60:240] = True
    mask[90:110, 140:160] = False  # a flower lying on the fabric
    filled = fill_holes(mask)
    assert filled[100, 150]
    assert not filled[10, 10]
    assert not filled[100, 280]


def test_empty_mask_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        compose(_photo(), np.zeros((360, 640), dtype=bool), Image.new("RGB", (10, 10)))


def test_corner_mark_avoids_the_product() -> None:
    img = Image.new("RGB", (400, 400), (230, 230, 230))
    mask = np.zeros((400, 400), dtype=bool)
    mask[200:, 200:] = True  # product fills the bottom-right quarter
    marked = np.asarray(add_corner_mark(img, mask))
    changed = np.any(marked != np.asarray(img), axis=2)
    assert changed.any()
    assert not changed[mask].any()


@pytest.mark.parametrize(("ai", "source"), [(True, COMPOSITE_SYNTHETIC), (False, PHOTO_ORIGINAL)])
def test_jpeg_carries_digital_source_type(ai: bool, source: str) -> None:
    data = save_jpeg(Image.new("RGB", (600, 600), "white"), ai_background=ai)
    assert data[:2] == b"\xff\xd8"
    img = Image.open(io.BytesIO(data))
    xmp = img.info["xmp"]
    assert source.encode() in xmp
    assert b"Iptc4xmpExt:DigitalSourceType" in xmp
    assert "exif" not in img.info


def test_loose_fragments_are_dropped_but_big_regions_kept() -> None:
    from engine.media.masks import keep_main_regions

    mask = np.zeros((400, 600), dtype=bool)
    mask[100:300, 50:250] = True  # can 1
    mask[100:300, 300:480] = True  # can 2, separate but large
    mask[20:24, 560:564] = True  # speckle
    mask[380:383, 10:13] = True  # speckle
    cleaned = keep_main_regions(mask)
    assert cleaned[200, 100] and cleaned[200, 400]
    assert not cleaned[21, 561] and not cleaned[381, 11]
    assert cleaned.sum() == mask[100:300, 50:250].sum() + mask[100:300, 300:480].sum()
    assert not keep_main_regions(np.zeros((10, 10), dtype=bool)).any()
