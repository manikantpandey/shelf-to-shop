"""Meta Model API providers (Muse Spark, Muse Voice Transcribe, SAM 3.1, Muse Image).

Request shapes follow dev.meta.ai/docs; design choices come from spikes/RESULTS.md.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import meta_sam_parser as sam
import numpy as np
from PIL import Image
from pydantic import BaseModel, Field

from engine.agents.structured import StructuredCaller, untrusted
from engine.config import EngineConfig
from engine.media.composite import fill_holes
from engine.media.masks import place_mask
from engine.pipeline.align import place_turns
from engine.pipeline.schemas import Box, DetectedProduct, Transcript
from engine.prices.tags import tag_price
from engine.providers.interfaces import MaskResult, Providers
from engine.providers.meta_client import MetaClient
from engine.providers.metered import Usage, metered_call
from engine.providers.resilience import Resilient
from engine.runlog import CallContext
from engine.spend import image_cost, sam_image_cost, transcribe_cost

PROVIDER = "meta"
VIDEO_FPS = 2.0  # spike 1: ~140 tokens per frame; 2 fps found every item in a 32 s clip


# --- Muse Spark: products and its own reading of the spoken prices -------------------------
class _Seen(BaseModel):
    description: str = Field(description="what the item is, e.g. 'red silk saree, gold border'")
    noun: str = Field(description="one or two words naming the item type, e.g. 'saree'")
    colour: str
    first_seen_s: float
    last_seen_s: float
    best_frame_s: float = Field(description="time of the clearest, least blurred view")
    box: Box | None = Field(description="item box at best_frame_s, in pixels of the frame")
    tag_text: str | None = Field(description="exact text of a price tag on or next to the item")


class _SeenList(BaseModel):
    products: list[_Seen]


class _Heard(BaseModel):
    item: int
    spoken_price_inr: int | None = Field(description="price the seller says for this item")
    spoken_words: str | None = Field(description="the seller's exact words for that price")


class _HeardList(BaseModel):
    items: list[_Heard]


# Two calls, as in the spikes: a vision-only listing (accurate in spike 1), then pairing prices to
# items identified by their on-screen times. One combined call drifted descriptions off their
# time windows in a real run.
VIDEO_TASK = (
    "This is a shop owner's phone video walking past their stock. List each distinct product "
    "for sale in the order it first appears, with times in seconds from the start. Give a box "
    "around the item at best_frame_s in pixels of a {w}x{h} frame. Copy any price tag text on or "
    "next to the item exactly, or null. Do not invent items; ignore shelves, walls and "
    "background stock that is never the focus."
)
PAIR_TASK = (
    "The seller says prices aloud in Hindi, English or a mix (for example 'ye neela wala barah "
    "sau' means this blue one is 1200 rupees). The items below are identified by when they are "
    "on screen. For each item give the price the seller says for it and their exact words. A "
    "price can be said just before an item appears or just after the camera has moved past it; "
    "use the seller's words (colour, 'agla'/next, 'peeche'/behind) to match it to the right "
    "item. Leave it null when no price is said for an item; never use a price tag for this."
)


class MetaVideo:
    def __init__(self, client: MetaClient, caller: StructuredCaller) -> None:
        self.client = client
        self.caller = caller

    async def analyse(
        self, ctx: CallContext, video: Path, width: int, height: int, duration_s: float
    ) -> list[DetectedProduct]:
        file_id = await self.client.upload_file(video.read_bytes(), "clip.mp4", "video/mp4")
        video_part = {"type": "input_video", "file_id": file_id, "fps": VIDEO_FPS}
        video_tokens = int(duration_s * VIDEO_FPS * 150) + 2000
        try:
            seen = await self.caller.run(
                ctx,
                output=_SeenList,
                instructions="You catalogue products for small shops.",
                content=[
                    video_part,
                    {"type": "input_text", "text": VIDEO_TASK.format(w=width, h=height)},
                ],
                estimate_input_tokens=video_tokens,
                effort="medium",
                max_output_tokens=16_000,
                inputs_summary={"duration_s": round(duration_s, 1), "fps": VIDEO_FPS},
            )
            products = to_products(seen.value.products, width, height, duration_s)
            if not products:
                return products
            listing = [
                {
                    "item": p.idx,
                    "on_screen_s": [p.first_seen_s, p.last_seen_s],
                    "looks_like": p.description,
                }
                for p in products
            ]
            heard = await self.caller.run(
                ctx,
                output=_HeardList,
                instructions="You match a seller's spoken prices to items in their video.",
                content=[
                    video_part,
                    {
                        "type": "input_text",
                        "text": PAIR_TASK + "\n" + untrusted("items", listing),
                    },
                ],
                estimate_input_tokens=video_tokens + 300 * len(products),
                effort="medium",
                max_output_tokens=16_000,
                inputs_summary={"items": len(products)},
            )
        finally:
            await self.client.delete_file(file_id)
        by_item = {h.item: h for h in heard.value.items}
        return [
            p.model_copy(
                update={
                    "spark_price_inr": h.spoken_price_inr
                    if (h.spoken_price_inr or 0) > 0
                    else None,
                    "spark_price_words": h.spoken_words,
                }
            )
            if (h := by_item.get(p.idx)) is not None
            else p
            for p in products
        ]


def _first_price(text: str | None) -> int | None:
    """The selling price printed on a sign or tag (never a discount, weight or phone number)."""
    return tag_price(text)


def _clamp_box(box: Box | None, width: int, height: int) -> Box | None:
    if box is None:
        return None
    x1, x2 = sorted((max(0, min(width - 1, box.x1)), max(0, min(width - 1, box.x2))))
    y1, y2 = sorted((max(0, min(height - 1, box.y1)), max(0, min(height - 1, box.y2))))
    return Box(x1=x1, y1=y1, x2=x2, y2=y2) if x2 - x1 > 4 and y2 - y1 > 4 else None


def to_products(
    seen: list[_Seen], width: int, height: int, duration_s: float
) -> list[DetectedProduct]:
    """Clamp model output to the clip and number items in order of appearance."""
    out: list[DetectedProduct] = []
    for item in sorted(seen, key=lambda s: s.first_seen_s):
        first = max(0.0, min(duration_s, item.first_seen_s))
        last = max(first, min(duration_s, item.last_seen_s))
        best = min(max(item.best_frame_s, first), last)
        out.append(
            DetectedProduct(
                idx=len(out) + 1,
                description=item.description,
                colour=item.colour,
                noun=item.noun.strip().lower() or "item",
                first_seen_s=first,
                last_seen_s=last,
                best_frame_s=best,
                box=_clamp_box(item.box, width, height),
                tag_text=item.tag_text,
                tag_price_inr=_first_price(item.tag_text),
            )
        )
    return out


# --- Muse Voice Transcribe ----------------------------------------------------------------
class MetaTranscriber:
    def __init__(self, client: MetaClient, model: str, resilient: Resilient) -> None:
        self.client = client
        self.model = model
        self.resilient = resilient

    async def transcribe(
        self,
        ctx: CallContext,
        wav: Path,
        duration_s: float,
        speech_spans: list[tuple[float, float]],
    ) -> Transcript:
        request = {
            "model": self.model,
            "audioEncoding": "WAV",
            "mode": "ENDPOINTING",
            "languageBias": ["Hindi", "English"],
        }
        data = wav.read_bytes()
        cost = transcribe_cost(duration_s)
        result = await metered_call(
            ctx,
            self.resilient,
            provider=PROVIDER,
            model=self.model,
            operation="transcribe",
            estimate_usd=cost,
            fn=lambda: self.client.transcribe(data, request),
            usage_of=lambda _body: Usage(cost),
            inputs_summary={"audio_s": round(duration_s, 1)},
            outputs_summary=lambda body: {"turns": len(body.get("turns", []))},
        )
        body = result.value
        turns = [
            (t["startMs"] / 1000, t["endMs"] / 1000, t.get("transcript", ""))
            for t in body.get("turns", [])
        ]
        if not turns and body.get("transcript"):
            turns = [(0.0, duration_s, body["transcript"])]
        chunks, mentions, timing = place_turns(turns, speech_spans)
        return Transcript(
            text=body.get("transcript", ""), chunks=chunks, mentions=mentions, timing=timing
        )


# --- SAM 3.1 -----------------------------------------------------------------------------
MIN_POINT_CONFIDENCE = 0.6


class MetaSegmenter:
    def __init__(self, client: MetaClient, model: str, resilient: Resilient) -> None:
        self.client = client
        self.model = model
        self.resilient = resilient

    async def _segment(
        self, ctx: CallContext, frame: Path, prompt: str, operation: str
    ) -> list[tuple[Any, np.ndarray]]:
        width, height = Image.open(frame).size
        payload = {
            "model": self.model,
            "input": [{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": "data:image/jpeg;base64,"
                 + base64.b64encode(frame.read_bytes()).decode("ascii")},
            ]}],
            "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
        }  # fmt: skip

        async def call() -> list[dict[str, Any]]:
            # Buffer events before parsing: the parser reading the socket itself drops long
            # streams (spike 2b).
            return [event async for event in self.client.stream_response(payload)]

        result = await metered_call(
            ctx,
            self.resilient,
            provider=PROVIDER,
            model=self.model,
            operation=operation,
            estimate_usd=sam_image_cost(1),
            fn=call,
            usage_of=lambda _events: Usage(sam_image_cost(1)),
            inputs_summary={"prompt": "points" if prompt.startswith("<") else prompt},
        )

        async def replay() -> AsyncIterator[dict[str, Any]]:
            for event in result.value:
                yield event

        parsed = await sam.parse_responses_stream(
            replay(), sam.image_segmentation_format()
        ).final_result()
        return [
            (rec, place_mask(rec, width, height)) for rec in parsed.records if rec.kind == "mask"
        ]

    async def cutout(
        self, ctx: CallContext, frame: Path, box: Box | None, noun: str
    ) -> MaskResult | None:
        width, height = Image.open(frame).size
        if box is not None:
            # Spark's boxes sit on the item but are loose (spike 2), so prompt with points
            # inside it rather than the box itself.
            cx, cy = box.centre()
            quarter = (box.x2 - box.x1) // 4
            points = [
                sam.PromptPoint(x=x, y=cy, label="positive")
                for x in (cx - quarter, cx, cx + quarter)
            ]
            prompt = sam.build_object_prompt(
                size=(width, height),
                objects=[sam.PromptObject(id=1, prompts=[sam.FramePrompt(frame=0, points=points)])],
            )
            found = await self._segment(ctx, frame, prompt, "segment_points")
            if found:
                rec, mask = max(found, key=lambda rm: rm[1].sum())
                if rec.confidence is None or rec.confidence >= MIN_POINT_CONFIDENCE:
                    return MaskResult(fill_holes(mask), rec.confidence, "point")
        # Fall back to the noun, keeping the mask that best covers the box (or the largest).
        found = await self._segment(ctx, frame, noun or "product", "segment_concept")
        if not found:
            return None

        def cover(mask: np.ndarray) -> float:
            if box is None:
                return float(mask.mean())
            return float(mask[box.y1 : box.y2, box.x1 : box.x2].mean())

        rec, mask = max(found, key=lambda rm: cover(rm[1]))
        return MaskResult(fill_holes(mask), rec.confidence, "concept")


# --- Muse Image ---------------------------------------------------------------------------
class MetaImages:
    def __init__(self, client: MetaClient, model: str, resilient: Resilient) -> None:
        self.client = client
        self.model = model
        self.resilient = resilient

    async def backdrop(self, ctx: CallContext, prompt: str) -> bytes:
        result = await metered_call(
            ctx,
            self.resilient,
            provider=PROVIDER,
            model=self.model,
            operation="backdrop",
            estimate_usd=image_cost(1),
            fn=lambda: self.client.generate_image(self.model, prompt, output_format="png"),
            usage_of=lambda _png: Usage(image_cost(1)),
            inputs_summary={"prompt": prompt[:120]},
        )
        return result.value


def meta_providers(config: EngineConfig) -> tuple[Providers, MetaClient]:
    """Providers backed by the Meta Model API. The caller closes the returned client."""
    if config.meta_api_key is None:
        raise ValueError("META_API_KEY is not set")
    client = MetaClient(
        config.meta_api_key.get_secret_value(),
        config.meta_base_url,
        timeout_s=config.request_timeout_s,
    )

    def resilient(name: str) -> Resilient:
        return Resilient(name, timeout_s=config.request_timeout_s)

    caller = StructuredCaller(client, config.models.vision, resilient("meta-spark"))
    providers = Providers(
        video=MetaVideo(client, caller),
        transcriber=MetaTranscriber(client, config.models.transcribe, resilient("meta-asr")),
        segmenter=MetaSegmenter(client, config.models.segment, resilient("meta-sam")),
        images=MetaImages(client, config.models.image, resilient("meta-image")),
        text=caller,
    )
    return providers, client
