"""Replacement product photos: the seller's own upload, a database packshot, or a re-cut from a
moment in the video that the seller tapped.

Every path ends in the same square 1024 px JPEG with no EXIF (no location, no camera data).
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from engine.export.provenance import save_jpeg
from engine.media.composite import EXPORT_SIZE, compose
from engine.media.masks import keep_main_regions
from engine.pipeline.schemas import Box
from engine.pipeline.segment import mask_quality
from engine.providers.interfaces import Segmenter
from engine.runlog import CallContext

MAX_PHOTO_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 40_000_000
ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
PLAIN_BACKDROP = (236, 236, 233)
# Half the side of the box drawn around the seller's tap, as a share of the frame.
TAP_BOX = 0.14
MIN_QUALITY = 0.3


class PhotoRejectedError(ValueError):
    """The file is not a usable photo; the message is safe to show the seller."""


def square_photo(data: bytes) -> bytes:
    """Validate an image file and return it as a padded square JPEG (no EXIF)."""
    if len(data) > MAX_PHOTO_BYTES:
        raise PhotoRejectedError("The photo is over 12 MB. Pick a smaller one.")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise PhotoRejectedError("Pick a JPEG, PNG or WebP photo.")
            if probe.width * probe.height > MAX_PIXELS:
                raise PhotoRejectedError("The photo is too large. Pick a smaller one.")
            probe.verify()
        with Image.open(io.BytesIO(data)) as raw:
            image = ImageOps.exif_transpose(raw)
            image.load()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise PhotoRejectedError("That file is not a photo. Pick a JPEG, PNG or WebP.") from exc
    if min(image.size) < 200:
        raise PhotoRejectedError("The photo is too small. Use one at least 500 pixels wide.")
    if image.mode in ("RGBA", "LA", "P"):
        flat = Image.new("RGB", image.size, "white")
        flat.paste(image.convert("RGBA"), mask=image.convert("RGBA").getchannel("A"))
        image = flat
    image = image.convert("RGB")
    image.thumbnail((EXPORT_SIZE, EXPORT_SIZE), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (EXPORT_SIZE, EXPORT_SIZE), "white")
    canvas.paste(image, ((EXPORT_SIZE - image.width) // 2, (EXPORT_SIZE - image.height) // 2))
    return save_jpeg(canvas, ai_background=False)


def tap_box(width: int, height: int, x: float, y: float) -> Box:
    """A box around the seller's tap (x, y in 0..1); the segmenter prompts points inside it."""
    cx, cy = min(max(x, 0.0), 1.0) * width, min(max(y, 0.0), 1.0) * height
    dx, dy = TAP_BOX * width, TAP_BOX * height
    return Box(
        x1=max(0, round(cx - dx)),
        y1=max(0, round(cy - dy)),
        x2=min(width - 1, round(cx + dx)),
        y2=min(height - 1, round(cy + dy)),
    )


async def recut(
    ctx: CallContext, segmenter: Segmenter, frame: Path, x: float, y: float, noun: str
) -> bytes | None:
    """Cut the tapped item out of `frame` onto a plain backdrop; None if nothing clean was found."""
    with Image.open(frame) as im:
        photo = im.convert("RGB")
    result = await segmenter.cutout(ctx, frame, tap_box(photo.width, photo.height, x, y), noun)
    if result is None or mask_quality(result) < MIN_QUALITY:
        return None
    mask = keep_main_regions(result.mask)
    if not np.asarray(mask).any():
        return None
    backdrop = Image.new("RGB", (512, 512), PLAIN_BACKDROP)
    return save_jpeg(compose(photo, mask, backdrop).image, ai_background=False)
