"""SAM 3.1 mask records -> full-frame boolean masks, and mask files on disk."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import meta_sam_parser as sam
import numpy as np
from PIL import Image


def place_mask(record: Any, width: int, height: int) -> np.ndarray:
    """Decode one mask record into a frame-sized mask.

    Masks arrive box-local, and large ones are downscaled (longest side capped at 1024, seen in
    spike 4), so the raster is stretched back over its box before it is placed.
    """
    raster = np.frombuffer(sam.decode_mask_to_raster(record.mask), dtype=np.uint8)
    local = raster.reshape(record.mask.height, record.mask.width).astype(bool)
    left, top = int(record.bounds.left), int(record.bounds.top)
    box_w = max(1, round(record.bounds.right - record.bounds.left))
    box_h = max(1, round(record.bounds.bottom - record.bounds.top))
    if local.shape != (box_h, box_w):
        stretched = Image.fromarray(local.astype(np.uint8) * 255).resize(
            (box_w, box_h), Image.Resampling.NEAREST
        )
        local = np.asarray(stretched) > 127
    full = np.zeros((height, width), dtype=bool)
    region = full[top : top + local.shape[0], left : left + local.shape[1]]
    region[:] = local[: region.shape[0], : region.shape[1]]
    return full


def save_mask(mask: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask.astype(np.uint8) * 255).save(path, optimize=True)


def load_mask(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("L")) > 127


def keep_main_regions(
    mask: np.ndarray, min_fraction: float = 0.15, work_width: int = 256
) -> np.ndarray:
    """Drop small loose fragments; keep every region at least `min_fraction` of the largest.

    Components are found on a downscaled copy (fast, pure Python), then applied to the full mask,
    so kept regions keep their full-resolution edges.
    """
    h, w = mask.shape
    if not mask.any():
        return mask
    scale = min(1.0, work_width / w)
    sw, sh = max(1, round(w * scale)), max(1, round(h * scale))
    small_img = Image.fromarray(mask.astype(np.uint8) * 255).resize((sw, sh), Image.Resampling.BOX)
    small = np.asarray(small_img) > 64
    labels = np.zeros(small.shape, dtype=np.int32)
    sizes = [0]
    for y0, x0 in zip(*np.nonzero(small), strict=True):
        if labels[y0, x0]:
            continue
        label = len(sizes)
        labels[y0, x0] = label
        stack, size = [(int(y0), int(x0))], 0
        while stack:
            y, x = stack.pop()
            size += 1
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < sh and 0 <= nx < sw and small[ny, nx] and not labels[ny, nx]:
                    labels[ny, nx] = label
                    stack.append((ny, nx))
        sizes.append(size)
    biggest = max(sizes)
    keep_ids = [i for i, s in enumerate(sizes) if i and s >= min_fraction * biggest]
    keep = np.isin(labels, keep_ids)
    # Grow one small pixel so edges of kept regions survive the nearest-neighbour upscale.
    grown = keep.copy()
    grown[1:] |= keep[:-1]
    grown[:-1] |= keep[1:]
    grown[:, 1:] |= keep[:, :-1]
    grown[:, :-1] |= keep[:, 1:]
    full = Image.fromarray(grown.astype(np.uint8) * 255).resize((w, h), Image.Resampling.NEAREST)
    return mask & (np.asarray(full) > 127)
