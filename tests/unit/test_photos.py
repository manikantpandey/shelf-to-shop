"""Replacement photos: file checks, tap boxes and the Open Food Facts URL guards."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from engine.pipeline.photos import PhotoRejectedError, square_photo, tap_box
from shelf.catalog.openfoodfacts import (
    PackPhoto,
    clean_query,
    full_size,
    image_url_ok,
    rank,
    thumb_size,
    valid_barcode,
)

IMG = "https://images.openfoodfacts.org/images/products/890/208/020/4052/front_en.7.400.jpg"


def _file(fmt: str, size: tuple[int, int] = (640, 480), exif: bool = False) -> bytes:
    buf = io.BytesIO()
    image = Image.new("RGB", size, "teal")
    if exif:
        data = image.getexif()
        data[0x010F] = "PhoneMaker"  # camera make
        image.save(buf, fmt, exif=data)
    else:
        image.save(buf, fmt)
    return buf.getvalue()


def test_small_photos_fill_the_square() -> None:
    out = square_photo(_file("JPEG", (500, 500)))
    with Image.open(io.BytesIO(out)) as im:
        assert im.size == (1024, 1024)
        # The photo's own colour reaches the edges: it was scaled up, not left small in the middle.
        assert im.getpixel((5, 5)) != (255, 255, 255)


def test_square_photo_pads_to_square_and_drops_exif() -> None:
    out = square_photo(_file("JPEG", (640, 480), exif=True))
    with Image.open(io.BytesIO(out)) as im:
        assert im.size == (1024, 1024)
        assert not im.getexif()
        assert im.getpixel((5, 5)) == (255, 255, 255)  # padding, not stretched


@pytest.mark.parametrize(
    "data",
    [b"plain text", _file("GIF"), _file("JPEG", (120, 120)), b"\xff\xd8" + b"0" * 100],
)
def test_square_photo_rejects_non_photos(data: bytes) -> None:
    with pytest.raises(PhotoRejectedError):
        square_photo(data)


def test_tap_box_stays_inside_the_frame() -> None:
    box = tap_box(1280, 720, 0.98, 0.02)
    assert 0 <= box.x1 < box.x2 <= 1279 and 0 <= box.y1 < box.y2 <= 719


def test_open_food_facts_guards() -> None:
    assert (
        clean_query('Haldiram\'s "nut" AND countries_tags:x*') == "Haldiram s nut countries tags x"
    )
    assert image_url_ok(IMG)
    assert full_size(IMG).endswith("front_en.7.full.jpg") and image_url_ok(full_size(IMG))
    assert thumb_size(IMG).endswith("front_en.7.200.jpg") and image_url_ok(thumb_size(IMG))
    for bad in (
        IMG.replace("https://", "http://"),
        IMG.replace("images.openfoodfacts.org", "evil.example"),
        "https://images.openfoodfacts.org/../../etc/passwd",
        "https://images.openfoodfacts.org/images/products/1/x.php",
    ):
        assert not image_url_ok(bad)
    assert valid_barcode("8902080204052") and not valid_barcode("89020802040521234")


def test_rank_prefers_matching_words_then_india() -> None:
    def photo(code: str, name: str, india: bool) -> PackPhoto:
        return PackPhoto(code=code, name=name, brand=None, image_url=IMG, india=india)

    ranked = rank(
        "haldiram peanuts",
        [photo("11111111", "Lemon pie", False), photo("22222222", "Salted peanuts", False),
         photo("33333333", "Haldiram Salted Peanuts", True), photo("44444444", "Peanuts", True)],
    )  # fmt: skip
    assert [p.code for p in ranked] == ["33333333", "44444444", "22222222"]


def test_rank_puts_the_product_above_the_brand_name() -> None:
    def photo(code: str, name: str, brand: str) -> PackPhoto:
        return PackPhoto(code=code, name=name, brand=brand, image_url=IMG, india=True)

    ranked = rank(
        "American Garden green olives jar",
        [photo("11111111", "American Garden Pancake Syrup", "American Garden"),
         photo("22222222", "Green olives", "American Garden")],
    )  # fmt: skip
    assert ranked[0].code == "22222222"
