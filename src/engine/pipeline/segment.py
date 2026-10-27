"""Pick the best cut-out for a product, trying a few nearby frames when the first is weak.

Real clips (spikes/RESULTS.md) showed single-frame cut-outs failing on transparent bottles, jars and
items half-hidden by a hand; a frame a second earlier or later is often clean.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from engine.pipeline.schemas import DetectedProduct
from engine.providers.errors import ProviderError
from engine.providers.interfaces import MaskResult, Segmenter
from engine.runlog import CallContext

GOOD_ENOUGH = 0.85
MAX_FRAMES = 3


def candidate_times(product: DetectedProduct, n: int = MAX_FRAMES) -> list[float]:
    """The best frame first, then up to two neighbours inside the item's on-screen window."""
    first, last = product.first_seen_s, product.last_seen_s
    step = min(1.0, (last - first) / 4) if last > first else 0.0
    times = [product.best_frame_s]
    for delta in (-step, step):
        t = round(min(last, max(first, product.best_frame_s + delta)), 2)
        if all(abs(t - seen) > 0.2 for seen in times):
            times.append(t)
    return times[:n]


def mask_quality(result: MaskResult | None) -> float:
    if result is None or not result.mask.any():
        return 0.0
    confidence = result.confidence if result.confidence is not None else 0.7
    coverage = float(result.mask.mean())
    plausible = 1.0 if 0.03 <= coverage <= 0.7 else 0.5
    return confidence * plausible


async def best_cutout(
    ctx: CallContext,
    segmenter: Segmenter,
    product: DetectedProduct,
    frame_at: Callable[[float, int], Awaitable[Path]],
) -> tuple[MaskResult, Path] | None:
    """Try candidate frames until one is good enough; return the best mask and its frame."""
    best: tuple[float, MaskResult, Path] | None = None
    for attempt, t in enumerate(candidate_times(product)):
        frame = await frame_at(t, attempt)
        try:
            result = await segmenter.cutout(ctx, frame, product.box, product.noun)
        except ProviderError:
            if attempt == 0 and len(candidate_times(product)) == 1:
                raise
            continue
        score = mask_quality(result)
        if result is not None and (best is None or score > best[0]):
            best = (score, result, frame)
        if score >= GOOD_ENOUGH:
            break
    if best is None:
        return None
    return best[1], best[2]
