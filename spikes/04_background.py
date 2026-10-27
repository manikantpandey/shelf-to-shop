"""Spike 4: can we replace a product photo's background while keeping product pixels exact?

Steps:
  1. Product photo: pass --photo PATH (jpg/png), or let Muse Image generate a test shelf photo.
  2. SAM 3.1 concept segmentation on the photo -> best mask.
  3. Muse Image generates an empty backdrop from a fixed prompt (never text from user media).
  4. Composite original masked pixels over the backdrop; assert masked pixels are identical.
  5. Control: ask /images/edits to "replace only the background" and measure how much the
     product region drifts, to see whether the model alone could be trusted.

Run: uv run python spikes/04_background.py [--photo PATH] [--concept saree]
Outputs go to spikes/out/04/ (gitignored).
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
from pathlib import Path
from typing import Any

import httpx
import meta_sam_parser as sam
import numpy as np
from PIL import Image

from _common import (
    OUT,
    PRICE_IMAGE_EACH,
    PRICE_SAM_PER_IMAGE,
    Timer,
    data_url,
    describe_error,
    load_env,
    meta_base_url,
    meta_headers,
    model_id,
    sse_events,
    write_json,
)

OUT_DIR = OUT / "04"
TEST_PHOTO_PROMPT = (
    "Phone photo of a folded blue cotton saree with a thin gold border lying on a wooden shop "
    "shelf, other folded fabrics partly visible around it, natural indoor light, slightly cluttered"
)
BACKDROP_PROMPT = (
    "Empty seamless photography backdrop, light warm grey paper sweep, soft even studio light, "
    "gentle shadow area on the floor, nothing else in frame, no objects, no text, no people"
)
EDIT_PROMPT = (
    "Replace only the background with a plain light grey studio backdrop. Keep the product exactly "
    "as it is: same shape, colours, folds, border and texture."
)


def generate_image(client: httpx.Client, prompt: str, size: str, fmt: str) -> tuple[bytes, int]:
    with Timer() as t:
        r = client.post(
            "/images/generations",
            json={
                "model": model_id("META_IMAGE_MODEL", "muse-image-1.0"),
                "prompt": prompt,
                "n": 1,
                "size": size,
                "output_format": fmt,
            },
        )
    if r.status_code != 200:
        raise SystemExit(f"images/generations failed: {describe_error(r)}")
    return base64.b64decode(r.json()["data"][0]["b64_json"]), t.ms


def edit_image(client: httpx.Client, photo: Path) -> tuple[bytes | None, int, str | None]:
    with Timer() as t:
        r = client.post(
            "/images/edits",
            json={
                "model": model_id("META_IMAGE_MODEL", "muse-image-1.0"),
                "prompt": EDIT_PROMPT,
                "images": [{"image_url": data_url(photo)}],
                "output_format": "png",
            },
        )
    if r.status_code != 200:
        return None, t.ms, describe_error(r)
    return base64.b64decode(r.json()["data"][0]["b64_json"]), t.ms, None


async def segment(photo: Path, concept: str) -> tuple[list[dict[str, Any]], int]:
    """Return one entry per matched object: id, confidence, full-frame boolean mask."""
    width, height = Image.open(photo).size
    payload = {
        "model": model_id("META_SEGMENT_MODEL", "sam-3.1"),
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": concept},
                    {"type": "input_image", "image_url": data_url(photo)},
                ],
            }
        ],
        "stream": True,
        "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
    }
    async with httpx.AsyncClient(
        base_url=meta_base_url(), headers=meta_headers(), timeout=120
    ) as client:
        with Timer() as t:
            async with client.stream("POST", "/responses", json=payload) as r:
                if r.status_code != 200:
                    await r.aread()
                    raise SystemExit(f"SAM request failed: {describe_error(r)}")
                parsed = sam.parse_responses_stream(sse_events(r), sam.image_segmentation_format())
                result = await parsed.final_result()

    print(f"SAM outcome={result.outcome} records={len(result.records)}")
    objects: list[dict[str, Any]] = []
    for rec in result.records:
        if rec.kind != "mask":
            continue
        raster = np.frombuffer(sam.decode_mask_to_raster(rec.mask), dtype=np.uint8)
        local = raster.reshape(rec.mask.height, rec.mask.width).astype(bool)
        left, top = int(rec.bounds.left), int(rec.bounds.top)
        box_w = round(rec.bounds.right - rec.bounds.left)
        box_h = round(rec.bounds.bottom - rec.bounds.top)
        print(
            f"  object {rec.object_id}: conf={rec.confidence} raster={rec.mask.width}x"
            f"{rec.mask.height} bounds=({rec.bounds.left},{rec.bounds.top})-"
            f"({rec.bounds.right},{rec.bounds.bottom}) box~{box_w}x{box_h}"
        )
        # Large masks arrive downscaled (observed: longest side capped at 1024), so stretch the
        # raster back over its box before placing it in the frame.
        scaled = local.shape != (box_h, box_w)
        if scaled:
            stretched = Image.fromarray(local.astype(np.uint8) * 255).resize(
                (box_w, box_h), Image.NEAREST
            )
            local = np.asarray(stretched) > 127
        full = np.zeros((height, width), dtype=bool)
        region = full[top : top + local.shape[0], left : left + local.shape[1]]
        region[:] = local[: region.shape[0], : region.shape[1]]
        objects.append(
            {
                "object_id": rec.object_id,
                "confidence": rec.confidence,
                "mask": full,
                "raster_scaled_to_box": scaled,
                "raster_size": [rec.mask.width, rec.mask.height],
                "bounds": [rec.bounds.left, rec.bounds.top, rec.bounds.right, rec.bounds.bottom],
            }
        )
    return objects, t.ms


def cover_resize(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Scale to cover `size`, then centre-crop (backdrop only; never applied to product pixels)."""
    w, h = size
    scale = max(w / img.width, h / img.height)
    resized = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1), Image.LANCZOS)
    left = (resized.width - w) // 2
    top = (resized.height - h) // 2
    return resized.crop((left, top, left + w, top + h))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--photo", type=Path)
    parser.add_argument("--concept", default="saree")
    args = parser.parse_args()
    load_env()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"concept": args.concept, "calls": []}
    cost = 0.0

    with httpx.Client(base_url=meta_base_url(), headers=meta_headers(), timeout=180) as client:
        if args.photo:
            photo = args.photo
        else:
            data, ms = generate_image(client, TEST_PHOTO_PROMPT, "1024x1024", "jpeg")
            photo = OUT_DIR / "test_photo.jpg"
            photo.write_bytes(data)
            cost += PRICE_IMAGE_EACH
            report["calls"].append({"call": "generate test photo", "latency_ms": ms})
        original = np.asarray(Image.open(photo).convert("RGB"))
        report["photo_size"] = [original.shape[1], original.shape[0]]

        objects, ms = asyncio.run(segment(photo, args.concept))
        cost += PRICE_SAM_PER_IMAGE
        report["calls"].append({"call": "sam-3.1 image", "latency_ms": ms, "objects": len(objects)})
        if not objects:
            write_json(OUT_DIR / "report.json", report)
            raise SystemExit(f"SAM found no '{args.concept}'. Try another --concept.")
        best = max(objects, key=lambda o: (o["confidence"] or 0, o["mask"].sum()))
        mask = best["mask"]
        report["mask"] = {
            "object_id": best["object_id"],
            "confidence": best["confidence"],
            "raster_size": best["raster_size"],
            "raster_scaled_to_box": best["raster_scaled_to_box"],
            "bounds": best["bounds"],
            "coverage_pct": round(100 * mask.mean(), 2),
        }
        Image.fromarray((mask * 255).astype(np.uint8)).save(OUT_DIR / "mask.png")

        backdrop_bytes, ms = generate_image(client, BACKDROP_PROMPT, "1024x1024", "png")
        cost += PRICE_IMAGE_EACH
        report["calls"].append({"call": "generate backdrop", "latency_ms": ms})
        backdrop = Image.open(io.BytesIO(backdrop_bytes)).convert("RGB")
        report["backdrop_returned_size"] = list(backdrop.size)
        backdrop.save(OUT_DIR / "backdrop.png")

        canvas = np.asarray(cover_resize(backdrop, (original.shape[1], original.shape[0]))).copy()
        canvas[mask] = original[mask]
        Image.fromarray(canvas).save(OUT_DIR / "composite.png")
        report["composite_masked_pixels_identical"] = bool(
            np.array_equal(canvas[mask], original[mask])
        )

        edited, ms, err = edit_image(client, photo)
        report["calls"].append({"call": "images/edits control", "latency_ms": ms, "error": err})
        if edited is not None:
            cost += PRICE_IMAGE_EACH
            edit_img = Image.open(io.BytesIO(edited)).convert("RGB")
            report["edit_returned_size"] = list(edit_img.size)
            edit_img.save(OUT_DIR / "edit_control.png")
            aligned = np.asarray(edit_img.resize((original.shape[1], original.shape[0])))
            diff = np.abs(aligned.astype(int) - original.astype(int)).max(axis=2)[mask]
            report["edit_product_drift"] = {
                "mean_abs_diff": round(float(diff.mean()), 2),
                "pct_pixels_diff_gt_10": round(100 * float((diff > 10).mean()), 2),
                "pct_pixels_identical": round(100 * float((diff == 0).mean()), 2),
            }

    report["estimated_cost_usd"] = round(cost, 4)
    write_json(OUT_DIR / "report.json", report)
    print({k: v for k, v in report.items() if k != "calls"})
    print("calls:", report["calls"])


if __name__ == "__main__":
    main()
