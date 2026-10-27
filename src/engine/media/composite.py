"""Place original product pixels on a generated backdrop.

Product pixels inside the mask are copied unchanged; only backdrop pixels are generated, shaded or
labelled. A final uniform resize (whole image, not a generative edit) brings it to export size.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

EXPORT_SIZE = 1024
MIN_FEED_SIDE = 500  # Meta catalog: images at least 500 x 500


def fill_holes(mask: np.ndarray, work_width: int = 320) -> np.ndarray:
    """Fill enclosed gaps (e.g. flowers lying on fabric) by flood-filling the outside."""
    h, w = mask.shape
    scale = min(1.0, work_width / w)
    small_size = (max(1, round(w * scale)), max(1, round(h * scale)))
    small = Image.fromarray(mask.astype(np.uint8) * 255).resize(small_size, Image.Resampling.BOX)
    # Background at low resolution where most of the area is background; pad so the border is
    # always reachable from the corner.
    bg = (np.asarray(small) < 128).astype(np.uint8) * 255
    # .copy(): fromarray can share the numpy buffer, and floodfill must write to a real image.
    padded = Image.fromarray(np.pad(bg, 1, constant_values=255)).copy()
    ImageDraw.floodfill(padded, (0, 0), 128)
    outside_small = np.asarray(padded)[1:-1, 1:-1] == 128
    outside = Image.fromarray(outside_small.astype(np.uint8) * 255).resize(
        (w, h), Image.Resampling.NEAREST
    )
    return mask | ~(np.asarray(outside) > 127)


def mask_bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        raise ValueError("empty mask")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    w, h = size
    scale = max(w / img.width, h / img.height)
    resized = img.resize(
        (max(w, round(img.width * scale)), max(h, round(img.height * scale))),
        Image.Resampling.LANCZOS,
    )
    left, top = (resized.width - w) // 2, (resized.height - h) // 2
    return resized.crop((left, top, left + w, top + h))


@dataclass(frozen=True)
class Composite:
    image: Image.Image  # final square RGB image at EXPORT_SIZE
    product_pixels_exact: bool  # masked pixels identical to the source before the final resize
    upscaled: bool


def _contact_shadow(size: tuple[int, int], box: tuple[int, int, int, int]) -> np.ndarray:
    """Soft elliptical shadow under the product's bottom edge, 0..1 darkness."""
    w, h = size
    x1, y1, x2, y2 = box
    layer = Image.new("L", (w, h), 0)
    bw, bh = x2 - x1, y2 - y1
    ellipse = (x1 + bw * 0.05, y2 - bh * 0.05, x2 - bw * 0.05, y2 + bh * 0.07)
    ImageDraw.Draw(layer).ellipse(ellipse, fill=150)
    blurred = layer.filter(ImageFilter.GaussianBlur(radius=max(4, bh * 0.04)))
    return np.asarray(blurred, dtype=np.float32) / 255.0


def compose(
    photo: Image.Image,
    mask: np.ndarray,
    backdrop: Image.Image,
    *,
    padding: float = 0.12,
    shadow: bool = True,
) -> Composite:
    """Square product shot: original masked pixels over the backdrop, centred with padding."""
    src = np.asarray(photo.convert("RGB"))
    if mask.shape != src.shape[:2]:
        raise ValueError("mask and photo sizes differ")
    x1, y1, x2, y2 = mask_bbox(mask)
    side = round(max(x2 - x1, y2 - y1) * (1 + 2 * padding))
    # Square canvas centred on the product, in source-pixel units (may extend past the photo).
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    ox, oy = round(cx - side / 2), round(cy - side / 2)

    canvas = np.asarray(cover(backdrop.convert("RGB"), (side, side)), dtype=np.float32)
    local_box = (x1 - ox, y1 - oy, x2 - ox, y2 - oy)
    if shadow:
        dark = _contact_shadow((side, side), local_box)[..., None]
        canvas = (canvas * (1 - 0.45 * dark)).astype(np.float32)
    out = np.clip(canvas, 0, 255).astype(np.uint8)

    # Copy product pixels last so nothing (shadow included) can touch them.
    ys, xs = np.nonzero(mask)
    out[ys - oy, xs - ox] = src[ys, xs]
    exact = bool(np.array_equal(out[ys - oy, xs - ox], src[ys, xs]))

    image = Image.fromarray(out)
    upscaled = side < EXPORT_SIZE
    if side != EXPORT_SIZE:
        image = image.resize((EXPORT_SIZE, EXPORT_SIZE), Image.Resampling.LANCZOS)
    return Composite(image=image, product_pixels_exact=exact, upscaled=upscaled)


def add_corner_mark(
    image: Image.Image, mask_in_image: np.ndarray, text: str = "AI background"
) -> Image.Image:
    """Small label in the corner that overlaps the product least."""
    img = image.convert("RGB").copy()
    w, h = img.size
    font = ImageFont.load_default(size=max(14, w // 48))
    draw = ImageDraw.Draw(img, "RGBA")
    left, top, right, bottom = (int(v) for v in draw.textbbox((0, 0), text, font=font))
    pad = max(6, w // 128)
    box_w, box_h = right - left + 2 * pad, bottom - top + 2 * pad
    margin = max(8, w // 64)
    corners: dict[str, tuple[int, int]] = {
        "bottom_right": (w - margin - box_w, h - margin - box_h),
        "bottom_left": (margin, h - margin - box_h),
        "top_right": (w - margin - box_w, margin),
        "top_left": (margin, margin),
    }

    def overlap(xy: tuple[int, int]) -> float:
        x, y = xy
        return float(mask_in_image[y : y + box_h, x : x + box_w].mean())

    x, y = min(corners.values(), key=overlap)
    draw.rounded_rectangle((x, y, x + box_w, y + box_h), radius=box_h // 2, fill=(20, 24, 29, 190))
    draw.text((x + pad - left, y + pad - top), text, font=font, fill=(255, 255, 255, 255))
    return img
