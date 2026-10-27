"""Turn everything doubtful into a short question for the seller."""

from __future__ import annotations

from statistics import median

from engine.pipeline.colours import colours_in
from engine.pipeline.schemas import Cutout, DetectedProduct, Flag, PriceDecision

OUTLIER_FACTOR = 5.0  # a price 5x above or below the job's median gets a second look
ABSOLUTE_MAX_INR = 5_00_000
MIN_MASK_CONFIDENCE = 0.7
MIN_MASK_COVERAGE = 0.02


def _iou(a: DetectedProduct, b: DetectedProduct) -> float:
    inter = max(0.0, min(a.last_seen_s, b.last_seen_s) - max(a.first_seen_s, b.first_seen_s))
    union = max(a.last_seen_s, b.last_seen_s) - min(a.first_seen_s, b.first_seen_s)
    return inter / union if union > 0 else 0.0


def verify(
    products: list[DetectedProduct],
    decisions: list[PriceDecision],
    cutouts: list[Cutout],
    match_flags: list[Flag],
) -> list[Flag]:
    flags = list(match_flags)
    asked_about = {c for f in flags if f.kind == "ambiguous_price" for c in f.candidates}

    for d in decisions:
        if d.price_inr is None and d.product_idx not in asked_about:
            flags.append(Flag(kind="missing_price", product_idx=d.product_idx,
                              question_key="flag.missing_price"))  # fmt: skip

    prices = [d.price_inr for d in decisions if d.price_inr is not None]
    mid = median(prices) if len(prices) >= 3 else None
    for d in decisions:
        p = d.price_inr
        if p is None:
            continue
        odd = p > ABSOLUTE_MAX_INR or (
            mid is not None and (p > mid * OUTLIER_FACTOR or p < mid / OUTLIER_FACTOR)
        )
        if odd:
            flags.append(
                Flag(
                    kind="implausible_price",
                    product_idx=d.product_idx,
                    question_key="flag.implausible_price",
                    params={"price": p, "typical": int(mid) if mid is not None else 0},
                    options=[p],
                )
            )

    for i, a in enumerate(products):
        for b in products[i + 1 :]:
            same_look = colours_in(a.colour) & colours_in(b.colour) and a.noun == b.noun
            if same_look and _iou(a, b) > 0.5:
                flags.append(
                    Flag(
                        kind="duplicate",
                        product_idx=b.idx,
                        question_key="flag.duplicate",
                        candidates=[a.idx, b.idx],
                    )
                )

    for c in cutouts:
        weak = (c.confidence is not None and c.confidence < MIN_MASK_CONFIDENCE) or (
            c.coverage < MIN_MASK_COVERAGE
        )
        if weak:
            flags.append(Flag(kind="low_conf_mask", product_idx=c.product_idx,
                              question_key="flag.low_conf_mask"))  # fmt: skip
    return flags
