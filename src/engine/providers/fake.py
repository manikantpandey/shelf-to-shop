"""Deterministic providers that replay a labelled clip (evals/labels/*.json).

Used for tests, the offline demo (PROVIDERS=fake) and the Playwright end-to-end run. They write
run-log entries with zero cost so a fake run looks like a real one.
"""

from __future__ import annotations

import io
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from engine.agents.structured import Effort, StructuredResult
from engine.pipeline.colours import colours_in
from engine.pipeline.schemas import (
    Box,
    DetectedProduct,
    TimedChunk,
    TimedMention,
    Transcript,
)
from engine.prices.hinglish import find_prices, likely_prices
from engine.providers.interfaces import M, MaskResult, Providers
from engine.runlog import CallContext, RunLogEntry

NOUNS = ("saree", "dupatta", "kurti", "chappal", "sandal", "shoe", "basket", "bangle")
_UNTRUSTED = re.compile(r'<untrusted source="(?P<src>[^"]+)">\n(?P<body>.*?)\n</untrusted>', re.S)


def _log(ctx: CallContext, operation: str, model: str = "fake") -> None:
    ctx.runlog.record(
        RunLogEntry(job_id=ctx.job_id, stage=ctx.stage, provider="fake", model=model,
                    operation=operation, latency_ms=0, attempts=1, cost_usd=Decimal(0))
    )  # fmt: skip


class Scenario:
    def __init__(self, labels: dict[str, Any]) -> None:
        self.labels = labels
        self.products: list[dict[str, Any]] = labels["products"]

    @classmethod
    def load(cls, path: Path) -> Scenario:
        return cls(json.loads(path.read_text(encoding="utf-8")))


class FakeVideo:
    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario

    async def analyse(
        self, ctx: CallContext, video: Path, width: int, height: int, duration_s: float
    ) -> list[DetectedProduct]:
        _log(ctx, "analyse_video")
        out = []
        for p in self.scenario.products:
            a, b = p["appears_s"]
            what = p["what"]
            colour = " and ".join(sorted(colours_in(what))) or "plain"
            noun = next((n for n in NOUNS if n in what.lower()), "item")
            out.append(
                DetectedProduct(
                    idx=p["n"],
                    description=what,
                    colour=colour,
                    noun=noun,
                    first_seen_s=a,
                    last_seen_s=min(b, duration_s) if duration_s else b,
                    best_frame_s=round((a + min(b, duration_s or b)) / 2, 2),
                    box=Box(x1=width // 4, y1=height // 4, x2=3 * width // 4, y2=3 * height // 4),
                    tag_text=f"Rs {p['tag_price_inr']}" if p.get("tag_price_inr") else None,
                    tag_price_inr=p.get("tag_price_inr"),
                    spark_price_inr=p.get("spoken_price_inr"),
                    spark_price_words=p.get("spoken_words"),
                )
            )
        return out


class FakeTranscriber:
    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario

    async def transcribe(
        self,
        ctx: CallContext,
        wav: Path,
        duration_s: float,
        speech_spans: list[tuple[float, float]],
    ) -> Transcript:
        _log(ctx, "transcribe")
        chunks: list[TimedChunk] = []
        mentions: list[TimedMention] = []
        for turn, p in enumerate(self.scenario.products):
            words = p.get("spoken_words") or ""
            start = p.get("spoken_at_s")
            if not words or start is None:
                continue
            end = p.get("spoken_end_s") or start + 1.0
            chunks.append(TimedChunk(start_s=start, end_s=end, text=words, turn=turn))
            for m in likely_prices(find_prices(words)):
                mentions.append(
                    TimedMention(
                        value_inr=m.value,
                        t_s=start,
                        words=m.text,
                        chunk=len(chunks) - 1,
                        confidence=m.confidence,
                    )
                )
        return Transcript(text=" ".join(c.text for c in chunks), chunks=chunks, mentions=mentions)


class FakeSegmenter:
    async def cutout(
        self, ctx: CallContext, frame: Path, box: Box | None, noun: str
    ) -> MaskResult | None:
        _log(ctx, "segment_points")
        width, height = Image.open(frame).size
        b = box or Box(x1=width // 4, y1=height // 4, x2=3 * width // 4, y2=3 * height // 4)
        yy, xx = np.mgrid[0:height, 0:width]
        cx, cy = b.centre()
        rx, ry = max(1, (b.x2 - b.x1) / 2), max(1, (b.y2 - b.y1) / 2)
        mask = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1
        return MaskResult(mask, 0.95, "point")


class FakeImages:
    async def backdrop(self, ctx: CallContext, prompt: str) -> bytes:
        _log(ctx, "backdrop")
        ramp = np.linspace(225, 200, 512, dtype=np.float32)[:, None, None]
        img = np.broadcast_to(ramp, (512, 512, 3)).astype(np.uint8)
        buf = io.BytesIO()
        Image.fromarray(img).save(buf, "PNG")
        return buf.getvalue()


class FakeText:
    """Answers structured calls from the untrusted 'products' block the pipeline sends."""

    async def run(
        self,
        ctx: CallContext,
        *,
        output: type[M],
        instructions: str,
        content: list[dict[str, Any]],
        estimate_input_tokens: int,
        effort: Effort = "low",
        max_output_tokens: int = 4096,
        inputs_summary: dict[str, Any] | None = None,
    ) -> StructuredResult[M]:
        _log(ctx, "structured")
        items: list[dict[str, Any]] = []
        for part in content:
            for m in _UNTRUSTED.finditer(part.get("text", "")):
                if m.group("src") == "products":
                    items = json.loads(m.group("body"))
        rows = []
        for item in items:
            desc = str(item.get("description", "item"))
            title = desc.split("(")[0].strip().capitalize()[:60] or "Item"
            rows.append({
                "idx": item["idx"],
                "title_en": title,
                "title_hi": title,
                "description_en": f"{title}. Ask on WhatsApp for size and stock.",
                "description_hi": f"{title}. साइज़ और स्टॉक के लिए WhatsApp पर पूछें।",
                "category": "saree" if "saree" in desc.lower() else "arts_crafts",
                "colour": item.get("colour") or "plain",
                "material": "cotton" if "cotton" in desc.lower() else None,
                "pattern": None,
            })  # fmt: skip
        value = output.model_validate({"items": rows})
        return StructuredResult(value, Decimal(0), 0, repaired=False)


def fake_providers(scenario: Scenario) -> Providers:
    return Providers(
        video=FakeVideo(scenario),
        transcriber=FakeTranscriber(scenario),
        segmenter=FakeSegmenter(),
        images=FakeImages(),
        text=FakeText(),
    )
