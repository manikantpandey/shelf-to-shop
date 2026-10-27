"""Pipeline runner: stages with cached, resumable outputs.

Each stage writes `stages/<name>.json` with a hash of its inputs. A rerun loads stages whose
inputs did not change, so after a failure only the failed stage (and what follows) runs again.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
from PIL import Image
from pydantic import BaseModel, Field

from engine.export.provenance import save_jpeg
from engine.media.composite import add_corner_mark, compose
from engine.media.ingest import IngestResult, ingest
from engine.media.masks import keep_main_regions, load_mask, save_mask
from engine.media.transcode import frame_at
from engine.pipeline.align import mentions_in_chunks
from engine.pipeline.enrich import enrich
from engine.pipeline.match import match_prices
from engine.pipeline.schemas import (
    Cutout,
    DetectedProduct,
    Enriched,
    FinalImage,
    Flag,
    PriceDecision,
    Transcript,
)
from engine.pipeline.verify import verify
from engine.prices.hinglish import PARSER_VERSION
from engine.providers.errors import ProviderError
from engine.providers.interfaces import Providers
from engine.runlog import CallContext

T = TypeVar("T", bound=BaseModel)

BACKDROP_PROMPT = (
    "Empty seamless photography backdrop, light warm grey paper sweep, soft even studio light, "
    "gentle shadow area on the floor, nothing else in frame, no objects, no text, no people"
)
STAGES = ["ingest", "detect", "transcribe", "segment", "enrich", "match", "verify", "backgrounds"]


class DetectOut(BaseModel):
    products: list[DetectedProduct]


class SegmentOut(BaseModel):
    cutouts: list[Cutout]


class MatchOut(BaseModel):
    decisions: list[PriceDecision]
    flags: list[Flag]


class EnrichOut(BaseModel):
    items: list[Enriched]


class VerifyOut(BaseModel):
    flags: list[Flag]


class BackgroundsOut(BaseModel):
    images: list[FinalImage]
    backdrop_ai: bool


class StageEvent(BaseModel):
    stage: str
    status: str  # running | done | cached | failed
    at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    error: str | None = None


class RunResult(BaseModel):
    ingest: IngestResult
    products: list[DetectedProduct]
    transcript: Transcript
    cutouts: list[Cutout]
    decisions: list[PriceDecision]
    enriched: list[Enriched]
    flags: list[Flag]
    images: list[FinalImage]


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


class Pipeline:
    def __init__(
        self,
        providers: Providers,
        work_dir: Path,
        ctx: CallContext,
        *,
        ai_mark: bool = True,
        on_event: Callable[[StageEvent], None] | None = None,
        segment_concurrency: int = 4,
    ) -> None:
        self.p = providers
        self.work = work_dir
        self.ctx = ctx
        self.ai_mark = ai_mark
        self.on_event = on_event or (lambda _e: None)
        self.segment_concurrency = segment_concurrency
        self.hashes: dict[str, str] = {}
        (self.work / "stages").mkdir(parents=True, exist_ok=True)

    def _emit(self, stage: str, status: str, error: str | None = None) -> None:
        event = StageEvent(stage=stage, status=status, error=error)
        with (self.work / "events.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(event.model_dump_json() + "\n")
        self.on_event(event)

    async def _stage(
        self,
        name: str,
        version: int,
        deps: dict[str, Any],
        out_type: type[T],
        fn: Callable[[], Awaitable[T]],
    ) -> T:
        key = _digest({"version": version, "deps": deps})
        path = self.work / "stages" / f"{name}.json"
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("hash") == key:
                self.hashes[name] = key
                self._emit(name, "cached")
                return out_type.model_validate(saved["output"])
        self._emit(name, "running")
        try:
            out = await fn()
        except Exception as exc:
            self._emit(name, "failed", f"{type(exc).__name__}: {exc}"[:500])
            raise
        path.write_text(
            json.dumps({"hash": key, "output": out.model_dump(mode="json")}, ensure_ascii=False),
            encoding="utf-8",
        )
        self.hashes[name] = key
        self._emit(name, "done")
        return out

    async def run(self, video: Path) -> RunResult:
        source = file_digest(video)
        media = await self._stage(
            "ingest", 1, {"video": source}, IngestResult,
            lambda: asyncio.to_thread(ingest, video, self.work / "ingest"),
        )  # fmt: skip
        spans = [(s.start_s, s.end_s) for s in media.speech]

        async def detect() -> DetectOut:
            products = await self.p.video.analyse(
                self.ctx.for_stage("detect"), media.video, media.width, media.height,
                media.duration_s,
            )  # fmt: skip
            return DetectOut(products=products)

        async def transcribe() -> Transcript:
            if media.audio is None:
                return Transcript(text="", chunks=[], mentions=[], timing="none")
            return await self.p.transcriber.transcribe(
                self.ctx.for_stage("transcribe"), media.audio, media.duration_s, spans
            )

        detected, transcript = await asyncio.gather(
            self._stage("detect", 2, {"ingest": self.hashes["ingest"]}, DetectOut, detect),
            self._stage("transcribe", 1, {"ingest": self.hashes["ingest"]}, Transcript, transcribe),
        )
        products = detected.products
        # Re-read prices from the (possibly cached) transcript with the current parser.
        transcript = transcript.model_copy(
            update={"mentions": mentions_in_chunks(transcript.chunks)}
        )

        segmented = await self._stage(
            "segment", 2, {"detect": self.hashes["detect"]}, SegmentOut,
            lambda: self._segment(products, media),
        )  # fmt: skip
        enriched = await self._stage(
            "enrich", 1, {"segment": self.hashes["segment"]}, EnrichOut,
            lambda: self._enrich(products, segmented.cutouts),
        )  # fmt: skip
        # Match with colours read from each product's photo, not the detector's text.
        photo_colours = {e.product_idx: e.colour for e in enriched.items}
        matched = await self._stage(
            "match", 2,
            {"detect": self.hashes["detect"], "transcribe": self.hashes["transcribe"],
             "enrich": self.hashes["enrich"], "parser": PARSER_VERSION},
            MatchOut, lambda: self._match(products, transcript, photo_colours),
        )  # fmt: skip
        verified = await self._stage(
            "verify", 1, {"match": self.hashes["match"], "segment": self.hashes["segment"]},
            VerifyOut, lambda: self._verify(products, matched, segmented.cutouts),
        )  # fmt: skip
        backgrounds = await self._stage(
            "backgrounds", 1, {"segment": self.hashes["segment"], "ai_mark": self.ai_mark},
            BackgroundsOut, lambda: self._backgrounds(segmented.cutouts),
        )  # fmt: skip
        return RunResult(
            ingest=media,
            products=products,
            transcript=transcript,
            cutouts=segmented.cutouts,
            decisions=matched.decisions,
            enriched=enriched.items,
            flags=verified.flags,
            images=backgrounds.images,
        )

    async def _segment(self, products: list[DetectedProduct], media: IngestResult) -> SegmentOut:
        out_dir = self.work / "segment"
        out_dir.mkdir(parents=True, exist_ok=True)
        sem = asyncio.Semaphore(self.segment_concurrency)
        ctx = self.ctx.for_stage("segment")

        async def one(p: DetectedProduct) -> Cutout | None:
            frame = out_dir / f"frame_{p.idx:02d}.jpg"
            await asyncio.to_thread(frame_at, media.video, p.best_frame_s, frame)
            async with sem:
                result = await self.p.segmenter.cutout(ctx, frame, p.box, p.noun)
            if result is None or not result.mask.any():
                return None
            # Real clips (spike on clip A-C): SAM leaves small loose fragments; drop them.
            mask = await asyncio.to_thread(keep_main_regions, result.mask)
            mask_path = out_dir / f"mask_{p.idx:02d}.png"
            save_mask(mask, mask_path)
            return Cutout(
                product_idx=p.idx,
                frame=frame,
                mask=mask_path,
                confidence=result.confidence,
                coverage=round(float(mask.mean()), 4),
                method=result.method,  # type: ignore[arg-type]
            )

        found = await asyncio.gather(*(one(p) for p in products))
        return SegmentOut(cutouts=[c for c in found if c is not None])

    async def _match(
        self,
        products: list[DetectedProduct],
        transcript: Transcript,
        photo_colours: dict[int, str],
    ) -> MatchOut:
        seen = [
            p.model_copy(update={"colour": photo_colours.get(p.idx) or p.colour}) for p in products
        ]
        result = match_prices(seen, transcript)
        return MatchOut(decisions=result.decisions, flags=result.flags)

    async def _enrich(self, products: list[DetectedProduct], cutouts: list[Cutout]) -> EnrichOut:
        items = await enrich(self.ctx.for_stage("enrich"), self.p.text, products, cutouts)
        return EnrichOut(items=items)

    async def _verify(
        self, products: list[DetectedProduct], matched: MatchOut, cutouts: list[Cutout]
    ) -> VerifyOut:
        return VerifyOut(flags=verify(products, matched.decisions, cutouts, matched.flags))

    async def _backgrounds(self, cutouts: list[Cutout]) -> BackgroundsOut:
        out_dir = self.work / "images"
        out_dir.mkdir(parents=True, exist_ok=True)
        ai = True
        try:
            png = await self.p.images.backdrop(self.ctx.for_stage("backgrounds"), BACKDROP_PROMPT)
            backdrop = Image.open(io.BytesIO(png)).convert("RGB")
        except ProviderError:
            # Image model down or over the cap: a plain backdrop (not AI, so no label).
            ai = False
            backdrop = Image.new("RGB", (512, 512), (236, 236, 233))

        def render(c: Cutout) -> FinalImage:
            mask = load_mask(c.mask)
            result = compose(Image.open(c.frame), mask, backdrop)
            image = result.image
            if ai and self.ai_mark:
                silhouette = compose(
                    Image.fromarray((mask * 255).astype(np.uint8)).convert("RGB"),
                    mask, Image.new("RGB", (8, 8), "black"), shadow=False,
                ).image  # fmt: skip
                image = add_corner_mark(image, np.asarray(silhouette.convert("L")) > 127)
            path = out_dir / f"product_{c.product_idx:02d}.jpg"
            path.write_bytes(save_jpeg(image, ai_background=ai))
            return FinalImage(product_idx=c.product_idx, path=path, ai_background=ai)

        images = await asyncio.gather(*(asyncio.to_thread(render, c) for c in cutouts))
        return BackgroundsOut(images=list(images), backdrop_ai=ai)
