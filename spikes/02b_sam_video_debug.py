"""Spike 2b: diagnose SAM 3.1 video streams that drop mid-way.

Streams one request and logs event types, sizes and timing until completion or failure, then tries
the same request without streaming.
Run: uv run python spikes/02b_sam_video_debug.py [--fps 2] [--objects 6] [--no-stream]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter
from typing import Any

import httpx
import meta_sam_parser as sam

from _common import OUT, describe_error, load_env, meta_base_url, meta_headers, require
from engine.media.ffmpeg import ffmpeg
from engine.providers.meta_client import MetaClient


async def main(fps: float, n_objects: int, stream: bool, confidence: bool) -> None:
    load_env()
    rep = json.loads((OUT / "01" / "synth_a_report.json").read_text(encoding="utf-8"))
    products = next(r for r in rep["runs"] if r["name"] == "1_vision")["products"][:n_objects]
    src = OUT / "01" / "synth_a" / "ingest" / "video_720p.mp4"
    low = OUT / "02" / "synth_a" / f"debug_{fps}fps.mp4"
    low.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg(["-y", "-i", src, "-vf", f"fps={fps}", "-c:v", "libx264", "-preset", "veryfast",
            "-an", low])  # fmt: skip
    objects = []
    for i, p in enumerate(products, 1):
        b = p["box"]
        objects.append(sam.PromptObject(id=i, prompts=[sam.FramePrompt(
            frame=round(p["best_frame_s"] * fps),
            points=[sam.PromptPoint(x=(b["x1"] + b["x2"]) // 2, y=(b["y1"] + b["y2"]) // 2,
                                    label="positive")])]))  # fmt: skip
    text = sam.build_object_prompt(size=(1280, 720), objects=objects)
    print("prompt:", text)
    async with MetaClient(require("META_API_KEY"), meta_base_url()) as meta:
        file_id = await meta.upload_file(low.read_bytes(), "low.mp4", "video/mp4")
    payload: dict[str, Any] = {
        "model": "sam-3.1",
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": text},
            {"type": "input_video", "file_id": file_id}]}],
        "stream": stream,
        "metadata": {"mask_encoding": "one_bit", **({"include_confidence": "true"} if confidence else {})},
    }  # fmt: skip
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            base_url=meta_base_url(), headers=meta_headers(),
            timeout=httpx.Timeout(900, connect=30),
        ) as client:  # fmt: skip
            if not stream:
                r = await client.post("/responses", json=payload)
                print("non-stream status", r.status_code, f"{time.perf_counter() - started:.1f}s",
                      describe_error(r) if r.status_code >= 400 else f"{len(r.content)} bytes")  # fmt: skip
                if r.status_code == 200:
                    body = r.json()
                    out = "".join(
                        c.get("text", "") for item in body.get("output", [])
                        for c in item.get("content", []) if c.get("type") == "output_text"
                    )  # fmt: skip
                    print(
                        "lines:",
                        out.count("<") and len(out.splitlines()),
                        "usage:",
                        body.get("usage"),
                    )
                return
            kinds: Counter[str] = Counter()
            received = 0
            first: float | None = None
            async with client.stream("POST", "/responses", json=payload) as r:
                print("status", r.status_code, dict(r.headers))
                try:
                    async for line in r.aiter_lines():
                        received += len(line)
                        if line.startswith("data:"):
                            if first is None:
                                first = time.perf_counter() - started
                            try:
                                ev = json.loads(line[5:])
                                kinds[ev.get("type", "?")] += 1
                                if ev.get("type") in (
                                    "response.failed",
                                    "error",
                                    "response.incomplete",
                                ):
                                    print("terminal:", json.dumps(ev)[:500])
                            except json.JSONDecodeError:
                                kinds["bad-json"] += 1
                                print("non-JSON data line:", line[:120])
                except httpx.HTTPError as exc:
                    print("stream broke:", type(exc).__name__, exc)
            print(f"first event {first}s, total {time.perf_counter() - started:.1f}s, "
                  f"{received} bytes, events {dict(kinds)}")  # fmt: skip
    finally:
        async with MetaClient(require("META_API_KEY"), meta_base_url()) as meta:
            await meta.delete_file(file_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fps", type=float, default=2)
    parser.add_argument("--objects", type=int, default=6)
    parser.add_argument("--no-stream", action="store_true")
    parser.add_argument("--confidence", action="store_true")
    a = parser.parse_args()
    asyncio.run(main(a.fps, a.objects, not a.no_stream, a.confidence))
