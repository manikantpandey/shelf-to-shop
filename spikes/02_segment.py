"""Spike 2: SAM 3.1 cut-outs for each detected product, image vs video mode, three prompt styles.

Uses spike 1's detections (best frame + Muse Spark box). Image mode tries, per product:
  box     the Spark box as a box prompt
  point   one positive point at the Spark box centre
  concept the noun "saree", keeping the mask that best covers the Spark box
Video mode tracks every product from its best frame (point prompts) on a 5 fps copy of the clip
and compares each track's extent to the labelled on-screen window.

Run after spike 1: uv run python spikes/02_segment.py [--clip synth_a]
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
from pathlib import Path
from typing import Any

import httpx
import meta_sam_parser as sam
import numpy as np
from PIL import Image, ImageDraw

from _common import (
    OUT,
    ROOT,
    Timer,
    describe_error,
    load_env,
    meta_base_url,
    meta_headers,
    sse_events,
    write_json,
)
from engine.media.ffmpeg import ffmpeg
from engine.providers.meta_client import MetaClient
from engine.spend import sam_image_cost, sam_video_cost

VIDEO_FPS = 2


def place_mask(rec: Any, width: int, height: int) -> np.ndarray:
    raster = np.frombuffer(sam.decode_mask_to_raster(rec.mask), dtype=np.uint8)
    local = raster.reshape(rec.mask.height, rec.mask.width).astype(bool)
    left, top = int(rec.bounds.left), int(rec.bounds.top)
    box_w = round(rec.bounds.right - rec.bounds.left)
    box_h = round(rec.bounds.bottom - rec.bounds.top)
    if local.shape != (box_h, box_w):
        img = Image.fromarray(local.astype(np.uint8) * 255).resize((box_w, box_h), Image.NEAREST)
        local = np.asarray(img) > 127
    full = np.zeros((height, width), dtype=bool)
    region = full[top : top + local.shape[0], left : left + local.shape[1]]
    region[:] = local[: region.shape[0], : region.shape[1]]
    return full


async def sam_stream(
    client: httpx.AsyncClient, text: str, media: dict[str, Any], fmt: Any
) -> tuple[Any, int]:
    payload = {
        "model": "sam-3.1",
        "input": [{"type": "message", "role": "user",
                   "content": [{"type": "input_text", "text": text}, media]}],
        "stream": True,
        "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
    }  # fmt: skip
    with Timer() as t:
        async with client.stream("POST", "/responses", json=payload) as r:
            if r.status_code != 200:
                await r.aread()
                raise RuntimeError(describe_error(r))
            # Buffer the events first: letting the parser pull from the socket directly drops
            # long video streams (spike 2b), and the payload is only a few hundred KB.
            events = [event async for event in sse_events(r)]

    async def replay() -> Any:
        for event in events:
            yield event

    result = await sam.parse_responses_stream(replay(), fmt).final_result()
    return result, t.ms


def box_cover(mask: np.ndarray, box: dict[str, int]) -> float:
    region = mask[box["y1"] : box["y2"], box["x1"] : box["x2"]]
    return float(region.mean()) if region.size else 0.0


def overlay(frame: Path, mask: np.ndarray | None, label: str) -> Image.Image:
    img = Image.open(frame).convert("RGB")
    if mask is not None:
        arr = np.asarray(img).copy()
        arr[~mask] = (arr[~mask] * 0.25).astype(np.uint8)
        img = Image.fromarray(arr)
    ImageDraw.Draw(img).text((10, 10), label, fill=(255, 255, 0))
    return img.resize((320, 180))


async def image_mode(products: list[dict[str, Any]], frames: list[Path]) -> list[dict[str, Any]]:
    w, h = Image.open(frames[0]).size
    sem = asyncio.Semaphore(6)
    async with httpx.AsyncClient(
        base_url=meta_base_url(), headers=meta_headers(), timeout=180
    ) as client:

        async def one(i: int, variant: str) -> dict[str, Any]:
            p, frame = products[i], frames[i]
            b = p["box"]
            media = {"type": "input_image",
                     "image_url": "data:image/jpeg;base64," + base64.b64encode(frame.read_bytes()).decode()}  # fmt: skip
            if variant == "box":
                text = sam.build_object_prompt(size=(w, h), objects=[sam.PromptObject(
                    id=1, prompts=[sam.FramePrompt(frame=0, box=sam.PromptBox(
                        left=b["x1"], top=b["y1"], right=b["x2"], bottom=b["y2"]))])])  # fmt: skip
            elif variant == "point":
                cx, cy = (b["x1"] + b["x2"]) // 2, (b["y1"] + b["y2"]) // 2
                text = sam.build_object_prompt(size=(w, h), objects=[sam.PromptObject(
                    id=1, prompts=[sam.FramePrompt(frame=0, points=[
                        sam.PromptPoint(x=cx, y=cy, label="positive")])])])  # fmt: skip
            else:
                text = "saree"
            async with sem:
                result, ms = await sam_stream(client, text, media, sam.image_segmentation_format())
            masks = [(rec, place_mask(rec, w, h)) for rec in result.records if rec.kind == "mask"]
            if not masks:
                return {"n": i + 1, "variant": variant, "ms": ms, "objects": 0, "mask": None}
            rec, mask = max(masks, key=lambda rm: box_cover(rm[1], b))
            return {
                "n": i + 1,
                "variant": variant,
                "ms": ms,
                "objects": len(masks),
                "confidence": rec.confidence,
                "frame_coverage": round(float(mask.mean()), 3),
                "spark_box_covered": round(box_cover(mask, b), 3),
                "mask": mask,
            }

        tasks = [one(i, v) for i in range(len(products)) for v in ("box", "point", "concept")]
        return list(await asyncio.gather(*tasks))


async def video_mode(
    products: list[dict[str, Any]], video: Path, work: Path, truth: list[dict[str, Any]]
) -> dict[str, Any]:
    low = work / f"video_{VIDEO_FPS}fps.mp4"
    ffmpeg(["-y", "-i", video, "-vf", f"fps={VIDEO_FPS}", "-c:v", "libx264", "-preset",
            "veryfast", "-an", low])  # fmt: skip
    w, h = 1280, 720
    objects = []
    for i, p in enumerate(products, 1):
        b = p["box"]
        cx, cy = (b["x1"] + b["x2"]) // 2, (b["y1"] + b["y2"]) // 2
        frame = round(p["best_frame_s"] * VIDEO_FPS)
        objects.append(sam.PromptObject(id=i, prompts=[sam.FramePrompt(
            frame=frame, points=[sam.PromptPoint(x=cx, y=cy, label="positive")])]))  # fmt: skip
    text = sam.build_object_prompt(size=(w, h), objects=objects)
    from _common import require

    async with MetaClient(require("META_API_KEY"), meta_base_url(), timeout_s=600) as meta:
        file_id = await meta.upload_file(low.read_bytes(), "low.mp4", "video/mp4")
    try:
        async with httpx.AsyncClient(
            base_url=meta_base_url(), headers=meta_headers(), timeout=600
        ) as client:
            result, ms = await sam_stream(
                client, text, {"type": "input_video", "file_id": file_id},
                sam.video_segmentation_format(),
            )  # fmt: skip
    finally:
        async with MetaClient(require("META_API_KEY"), meta_base_url()) as meta:
            await meta.delete_file(file_id)
    frames_by_obj: dict[str, list[int]] = {}
    for rec in result.records:
        if rec.kind == "mask" and rec.frame is not None:
            frames_by_obj.setdefault(str(rec.object_id), []).append(rec.frame.frame_index)
    tracks = []
    for gt in truth:
        seen = sorted(frames_by_obj.get(str(gt["n"]), []))
        if not seen:
            tracks.append({"n": gt["n"], "frames": 0})
            continue
        span = (seen[0] / VIDEO_FPS, seen[-1] / VIDEO_FPS)
        a, b2 = gt["appears_s"]
        inter = max(0.0, min(span[1], b2) - max(span[0], a))
        union = max(span[1], b2) - min(span[0], a)
        tracks.append({"n": gt["n"], "frames": len(seen), "track_s": [round(s, 1) for s in span],
                       "window_s": gt["appears_s"], "iou": round(inter / union, 2)})  # fmt: skip
    total_frames = int(32 * VIDEO_FPS)
    return {"latency_ms": ms, "outcome": str(result.outcome), "frames_billed_est": total_frames,
            "cost_usd_est": str(sam_video_cost(total_frames)), "tracks": tracks}  # fmt: skip


async def run(clip: str, video_only: bool) -> None:
    load_env()
    rep = json.loads((OUT / "01" / f"{clip}_report.json").read_text(encoding="utf-8"))
    products = next(r for r in rep["runs"] if r["name"] == "1_vision")["products"]
    truth = json.loads((ROOT / "evals" / "labels" / f"{clip}.json").read_text(encoding="utf-8"))
    work = OUT / "02" / clip
    work.mkdir(parents=True, exist_ok=True)
    frames = [OUT / "01" / clip / "best" / f"p{i}.jpg" for i in range(1, len(products) + 1)]
    video = OUT / "01" / clip / "ingest" / "video_720p.mp4"

    results: list[dict[str, Any]] = []
    if video_only:
        prev = (
            json.loads((work / "report.json").read_text(encoding="utf-8"))
            if (work / "report.json").exists()
            else {}
        )
        results = prev.get("image_mode", [])
    else:
        results = await image_mode(products, frames)
    tiles = []
    if not video_only:
        for r in results:
            tiles.append(overlay(frames[r["n"] - 1], r["mask"], f"{r['n']} {r['variant']}"))
            r.pop("mask")
        sheet = Image.new("RGB", (960, 180 * len(products)), "white")
        for k, tile in enumerate(tiles):
            sheet.paste(tile, ((k % 3) * 320, (k // 3) * 180))
        sheet.save(work / "image_mode_sheet.jpg", quality=85)
        for r in results:
            print("image", r)
        write_json(work / "report.json", {"image_mode": results})

    video_report = await video_mode(products, video, work, truth["products"])
    print("video", {k: v for k, v in video_report.items() if k != "tracks"})
    for t in video_report["tracks"]:
        print("   ", t)
    write_json(work / "report.json", {
        "image_mode": results,
        "image_cost_usd_est": str(sam_image_cost(len(results))),
        "video_mode": video_report,
    })  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clip", default="synth_a")
    parser.add_argument("--video-only", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.clip, args.video_only))


if __name__ == "__main__":
    main()
