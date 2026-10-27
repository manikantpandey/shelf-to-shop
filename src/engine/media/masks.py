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
