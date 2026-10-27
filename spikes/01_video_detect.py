"""Spikes 1 and 1b: what Muse Spark gets from a shelf walkthrough video.

1:  distinct products with time ranges, best frame, box and visible tag text (vision only).
1b: the same, plus each product's spoken price and when it was said, in one call (video + audio).
Both are scored against evals/labels/<clip>.json.

Run: uv run python spikes/01_video_detect.py [--clip synth_a] [--fps 2]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from _common import OUT, ROOT, load_env, meta_base_url, require, write_json
from engine.agents.structured import StructuredCaller
from engine.config import SpendCaps
from engine.media.ingest import ingest
from engine.providers.meta_client import MetaClient
from engine.providers.resilience import Resilient
from engine.runlog import CallContext, MemoryRunLog
from engine.spend import InMemorySpendLedger


class Box(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int


class SeenProduct(BaseModel):
    description: str = Field(description="what the item is, e.g. 'red silk saree, gold border'")
    colour: str
    first_seen_s: float
    last_seen_s: float
    best_frame_s: float = Field(description="time of the clearest, least blurred view")
    box: Box | None = Field(description="item box at best_frame_s, pixels of the frame")
    tag_text: str | None = Field(description="exact text of a price tag on or next to the item")


class SeenProducts(BaseModel):
    products: list[SeenProduct]


class PricedProduct(SeenProduct):
    spoken_price_inr: int | None = Field(description="price the seller says for this item")
    spoken_at_s: float | None = Field(description="when the seller starts saying that price")
    spoken_words: str | None = Field(description="the seller's words for that price")


class PricedProducts(BaseModel):
    products: list[PricedProduct]


VISION_TASK = (
    "This is a shop owner's phone video walking past their stock. List each distinct product "
    "for sale, in the order it first appears. Use times in seconds from the start of the video. "
    "Give a box around the item at best_frame_s in pixels of a {w}x{h} frame. Copy any price tag "
    "text on or next to the item exactly; leave it null if none. Do not invent items; ignore "
    "shelves, walls and background stock that is never the focus."
)
PRICE_TASK = (
    VISION_TASK + " The seller says prices aloud in Hindi, English or a mix (for example 'ye "
    "neela wala barah sau' means this blue one is 1200 rupees). For each item give the price the "
    "seller says for it, when they start saying it and their exact words. A price can be said "
    "just before an item appears or just after the camera has moved past it; match it to the "
    "item it describes. Leave the price null if no price is said for an item; never take a "
    "price from a tag for spoken_price_inr."
)


def iou(a: tuple[float, float], b: tuple[float, float]) -> float:
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union > 0 else 0.0


def score(pred: list[dict[str, Any]], truth: list[dict[str, Any]]) -> dict[str, Any]:
    pairs, used = [], set()
    for gt in truth:
        best, best_iou = None, 0.0
        for i, p in enumerate(pred):
            if i in used:
                continue
            v = iou((p["first_seen_s"], p["last_seen_s"]), tuple(gt["appears_s"]))
            if v > best_iou:
                best, best_iou = i, v
        if best is not None and best_iou >= 0.2:
            used.add(best)
        pairs.append((gt, pred[best] if best is not None and best_iou >= 0.2 else None, best_iou))
    rows = []
    for gt, p, v in pairs:
        row: dict[str, Any] = {"n": gt["n"], "matched": p is not None, "time_iou": round(v, 2)}
        if p is not None:
            row["best_frame_in_window"] = (
                gt["appears_s"][0] <= p["best_frame_s"] <= gt["appears_s"][1]
            )
            row["tag_text"] = p.get("tag_text")
            if "spoken_price_inr" in p:
                row["price_ok"] = p["spoken_price_inr"] == gt["spoken_price_inr"]
                row["pred_price"] = p["spoken_price_inr"]
                if gt["spoken_at_s"] is not None and p.get("spoken_at_s") is not None:
                    row["spoken_at_err_s"] = round(p["spoken_at_s"] - gt["spoken_at_s"], 2)
        rows.append(row)
    matched = sum(r["matched"] for r in rows)
    summary: dict[str, Any] = {
        "recall": f"{matched}/{len(truth)}",
        "precision": f"{matched}/{len(pred)}",
        "rows": rows,
    }
    if any("price_ok" in r for r in rows):
        summary["price_accuracy"] = f"{sum(r.get('price_ok', False) for r in rows)}/{len(truth)}"
    return summary


async def run(clip: str, fps: float) -> None:
    load_env()
    src = ROOT / "evals" / "videos" / f"{clip}.mp4"
    labels = json.loads((ROOT / "evals" / "labels" / f"{clip}.json").read_text(encoding="utf-8"))
    work = ROOT / "spikes" / "out" / "01" / clip
    media = ingest(src, work / "ingest")
    print(f"ingest: {media.width}x{media.height} {media.duration_s:.1f}s fps={media.fps:.1f}")

    report: dict[str, Any] = {"clip": clip, "fps": fps, "runs": []}
    async with MetaClient(require("META_API_KEY"), meta_base_url(), timeout_s=300) as client:
        file_id = await client.upload_file(media.video.read_bytes(), "clip.mp4", "video/mp4")
        try:
            jobs = [
                ("1_vision", "muse-spark-1.3", SeenProducts, VISION_TASK),
                ("1b_priced", "muse-spark-1.3", PricedProducts, PRICE_TASK),
                ("1b_priced", "muse-spark-1.2", PricedProducts, PRICE_TASK),
            ]
            for name, model, schema, task in jobs:
                log = MemoryRunLog()
                ledger = InMemorySpendLedger(SpendCaps(per_job_usd=Decimal("1.00")))
                ctx = CallContext(f"spike-{name}", "spike", ledger, log, stage=name)
                caller = StructuredCaller(client, model, Resilient("meta", timeout_s=300))
                content = [
                    {"type": "input_video", "file_id": file_id, "fps": fps},
                    {"type": "input_text", "text": task.format(w=media.width, h=media.height)},
                ]
                try:
                    result = await caller.run(
                        ctx, output=schema, instructions="You catalogue products for small shops.",
                        content=content, estimate_input_tokens=60_000, effort="medium",
                        max_output_tokens=16_000,
                    )  # fmt: skip
                except Exception as exc:  # spike: record and continue with the next variant
                    report["runs"].append({"name": name, "model": model, "error": str(exc)})
                    print(name, model, "ERROR", exc)
                    continue
                entry = log.entries[-1]
                pred = [p.model_dump() for p in result.value.products]
                run_report = {
                    "name": name,
                    "model": model,
                    "latency_ms": result.latency_ms,
                    "input_tokens": entry.input_tokens,
                    "output_tokens": entry.output_tokens,
                    "cost_usd": str(result.cost_usd),
                    "repaired": result.repaired,
                    "products": pred,
                    "score": score(pred, labels["products"]),
                }
                report["runs"].append(run_report)
                print(
                    name, model, f"{result.latency_ms} ms", f"in={entry.input_tokens}",
                    f"out={entry.output_tokens}", f"${result.cost_usd}",
                    json.dumps({k: v for k, v in run_report["score"].items() if k != "rows"}),
                )  # fmt: skip
                for row in run_report["score"]["rows"]:
                    print("   ", row)
        finally:
            await client.delete_file(file_id)
    write_json(OUT / "01" / f"{clip}_report.json", report)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clip", default="synth_a")
    parser.add_argument("--fps", type=float, default=2.0)
    args = parser.parse_args()
    asyncio.run(run(args.clip, args.fps))


if __name__ == "__main__":
    main()
