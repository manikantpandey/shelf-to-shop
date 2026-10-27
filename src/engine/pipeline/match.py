"""Match spoken prices to products, deterministically, keeping evidence for every decision.

Signals for "price P heard at time t belongs to product X":
  time    t inside X's on-screen window (1.0), fading to 0 over LEAD_S before / LAG_S after it
  colour  a colour word in the price's phrase (or the phrases beside it) matches X's colour
  vision  Muse Spark, watching and listening to the video, gave X the same price
A clear winner takes the price; a near-tie becomes a question for the seller, never a guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from engine.pipeline.colours import colours_in
from engine.pipeline.schemas import (
    DetectedProduct,
    Evidence,
    Flag,
    PriceDecision,
    TimedMention,
    Transcript,
)

LEAD_S = 4.0  # a price can be said this long before its item appears
LAG_S = 4.0  # ... or this long after the camera has moved on
COLOUR_WEIGHT = 0.6
DIRECTION_WEIGHT = 0.3
VISION_WEIGHT = 1.0
MARGIN = 0.15

# "agla wala" (the next one) / "peeche wala" (the one behind): which way along the shelf.
_NEXT = re.compile(r"(?i)\b(agla|agli|agle|next)\b|अगला|अगली|अगले")
_PREVIOUS = re.compile(r"(?i)\b(pichla|pichli|peeche|piche|previous)\b|पिछला|पिछली|पीछे")


def time_affinity(t: float, product: DetectedProduct) -> float:
    if product.first_seen_s <= t <= product.last_seen_s:
        return 1.0
    if t < product.first_seen_s:
        return max(0.0, 1 - (product.first_seen_s - t) / LEAD_S)
    return max(0.0, 1 - (t - product.last_seen_s) / LAG_S)


@dataclass(frozen=True)
class Context:
    """What the seller said around a price: the price's phrase and the phrases beside it."""

    colours: set[str]
    points_next: bool
    points_back: bool


CONTEXT_GAP_S = 2.0  # neighbouring phrases closer than this count as the same remark
# Phrases that start a new item: 'ye ...', 'aur ye ...', 'this ...'.
_NEW_ITEM = re.compile(r"(?i)^(?:aur\s+|and\s+)?(?:ye|yeh|yah|this)\b|^(?:और\s+)?(?:ये|यह)(?:\s|$)")


def context_of(transcript: Transcript, mention: TimedMention) -> Context:
    """The price's phrase plus the phrase before and after it, if spoken close in time.

    Turn boundaries are not used: the ASR sometimes makes every short phrase its own turn.
    """
    chunks = transcript.chunks
    k = mention.chunk
    parts = [chunks[k].text]
    if k > 0 and chunks[k].start_s - chunks[k - 1].end_s <= CONTEXT_GAP_S:
        parts.insert(0, chunks[k - 1].text)
    # The next phrase usually describes the next item ("... dedh hazaar. aur ye gulabi wala"),
    # so it only counts when it doesn't open a new item.
    if (
        k + 1 < len(chunks)
        and chunks[k + 1].start_s - chunks[k].end_s <= CONTEXT_GAP_S
        and not _NEW_ITEM.match(chunks[k + 1].text.strip())
    ):
        parts.append(chunks[k + 1].text)
    text = " ".join(parts)
    return Context(colours_in(text), bool(_NEXT.search(text)), bool(_PREVIOUS.search(text)))


def score(mention: TimedMention, product: DetectedProduct, ctx: Context) -> float:
    t = mention.t_s
    s = time_affinity(t, product)
    if s <= 0:
        return 0.0
    # Colour comes from the product photo (enrichment) when available, not the detector text.
    if ctx.colours & colours_in(product.colour):
        s += COLOUR_WEIGHT
    if (ctx.points_next and product.first_seen_s > t) or (
        ctx.points_back and product.last_seen_s < t
    ):
        s += DIRECTION_WEIGHT
    if product.spark_price_inr == mention.value_inr:
        s += VISION_WEIGHT
    return s


@dataclass
class MatchResult:
    decisions: list[PriceDecision]
    flags: list[Flag]
    unplaced: list[TimedMention] = field(default_factory=list)


def match_prices(products: list[DetectedProduct], transcript: Transcript) -> MatchResult:
    flags: list[Flag] = []
    unplaced: list[TimedMention] = []
    heard: dict[int, list[tuple[float, TimedMention]]] = {p.idx: [] for p in products}

    for mention in transcript.mentions:
        ctx = context_of(transcript, mention)
        ranked = sorted(((score(mention, p, ctx), p.idx) for p in products), reverse=True)
        if not ranked or ranked[0][0] <= 0:
            unplaced.append(mention)
            continue
        best_score, best_idx = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
        if best_score - runner_up < MARGIN:
            candidates = [idx for s, idx in ranked if s > 0 and best_score - s < MARGIN]
            flags.append(
                Flag(
                    kind="ambiguous_price",
                    product_idx=None,
                    question_key="flag.ambiguous_price",
                    params={"price": mention.value_inr, "said_at_s": round(mention.t_s)},
                    options=[mention.value_inr],
                    candidates=candidates,
                )
            )
            continue
        heard[best_idx].append((best_score, mention))

    decisions = [_decide(p, sorted(heard[p.idx], key=lambda x: -x[0]), flags) for p in products]
    return MatchResult(decisions=decisions, flags=flags, unplaced=unplaced)


def _decide(
    product: DetectedProduct, heard: list[tuple[float, TimedMention]], flags: list[Flag]
) -> PriceDecision:
    evidence = [
        Evidence(kind="speech", value_inr=m.value_inr, t_s=m.t_s, snippet=m.words) for _, m in heard
    ]
    vision = product.spark_price_inr
    if vision is not None:
        evidence.append(
            Evidence(kind="vision_pairing", value_inr=vision, snippet=product.spark_price_words)
        )
    if product.tag_price_inr is not None:
        evidence.append(Evidence(kind="tag", value_inr=product.tag_price_inr,
                                 snippet=product.tag_text))  # fmt: skip

    price: int | None
    if heard:
        top = heard[0][1]
        price, source = top.value_inr, "spoken"
        if vision == price:
            confidence = 0.95
        elif vision is None:
            confidence = 0.75
        else:
            confidence = 0.5
            flags.append(_conflict(product.idx, "vision", [price, vision]))
        if top.confidence < 0.6 and vision != price:
            flags.append(
                Flag(
                    kind="uncertain_price",
                    product_idx=product.idx,
                    question_key="flag.uncertain_price",
                    params={"price": price, "heard": top.words},
                    options=[price] + ([vision] if vision is not None else []),
                )
            )
        others = sorted({m.value_inr for _, m in heard} - {price})
        if others:
            flags.append(_conflict(product.idx, "multiple", [price, *others]))
    elif vision is not None:
        price, source, confidence = vision, "vision_pairing", 0.6
    elif product.tag_price_inr is not None:
        price, source, confidence = product.tag_price_inr, "tag", 0.6
    else:
        price, source, confidence = None, "none", 0.0

    tag = product.tag_price_inr
    if tag is not None and price is not None and tag != price:
        flags.append(_conflict(product.idx, "tag", [price, tag]))
    return PriceDecision(
        product_idx=product.idx,
        price_inr=price,
        source=source,  # type: ignore[arg-type]
        confidence=confidence,
        evidence=evidence,
    )


def _conflict(product_idx: int, against: str, options: list[int]) -> Flag:
    return Flag(
        kind="price_conflict",
        product_idx=product_idx,
        question_key=f"flag.price_conflict.{against}",
        params={"first": options[0], "second": options[1]},
        options=options,
    )
