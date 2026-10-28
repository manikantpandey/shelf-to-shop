"""Score one pipeline run against a labelled clip. Pure functions, no model calls, unit-tested."""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from typing import Any

from engine.pipeline.run import RunResult

PRICE_FLAGS = {"missing_price", "price_conflict", "ambiguous_price", "implausible_price",
               "uncertain_price"}  # fmt: skip
# Seeded errors that are only handled by asking the seller; taking either price silently is wrong.
MUST_ASK = {"price_conflict"}
SLACK_S = 1.0  # labels are hand-timed; allow a second either side
_STOP = {"the", "and", "with", "pack", "packs", "small", "large", "plastic", "bottle", "in", "of"}


@dataclass
class Score:
    clip: str
    seconds_of_video: float
    labelled: int
    found: int
    matched: int
    with_price: int
    right: int
    asked: int
    wrong: int
    seeded: int
    caught: int
    processing_s: float
    cost_usd: float

    @property
    def recall(self) -> float:
        return self.matched / self.labelled if self.labelled else 0.0

    @property
    def precision(self) -> float:
        return self.matched / self.found if self.found else 0.0


def total(scores: list[Score]) -> Score:
    sums = {
        f.name: sum(getattr(s, f.name) for s in scores) for f in fields(Score) if f.name != "clip"
    }
    return Score(clip="all", **sums)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2 and w not in _STOP}


def _overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union > 0 else 0.0


def match(labels: list[dict[str, Any]], result: RunResult) -> dict[int, int]:
    """Labelled item number -> detected product idx. Items must share screen time; among those,
    the pair with the most time overlap plus description overlap wins (greedy, one to one)."""
    pairs = []
    for label in labels:
        start, end = float(label["appears_s"][0]), float(label["appears_s"][1])
        said = _words(label["what"])
        for p in result.products:
            seen = (p.first_seen_s, p.last_seen_s)
            if _overlap((start - SLACK_S, end + SLACK_S), seen) <= 0:
                continue
            desc = _words(f"{p.colour} {p.noun} {p.description} {p.tag_text or ''}")
            text = len(said & desc) / len(said | desc) if said | desc else 0.0
            pairs.append((_overlap((start, end), seen) + text, label["n"], p.idx))
    out: dict[int, int] = {}
    for _, n, idx in sorted(pairs, reverse=True):
        if n not in out and idx not in out.values():
            out[n] = idx
    return out


def outcomes(labels: list[dict[str, Any]], result: RunResult) -> dict[int, str]:
    """Per labelled item that has a price: right, asked, wrong (silent) or missed (not found)."""
    pairs = match(labels, result)
    decisions = {d.product_idx: d.price_inr for d in result.decisions}
    asked = set()
    for f in result.flags:
        if f.kind in PRICE_FLAGS:
            asked.update([f.product_idx] if f.product_idx is not None else f.candidates)
    out = {}
    for label in labels:
        truth = label.get("spoken_price_inr") or label.get("tag_price_inr")
        if truth is None:
            continue
        idx = pairs.get(label["n"])
        if idx is None:
            out[label["n"]] = "missed"
        elif idx in asked:
            out[label["n"]] = "asked"
        elif decisions.get(idx) == truth:
            out[label["n"]] = "right"
        else:
            out[label["n"]] = "wrong"
    return out


def score(clip: str, labels: dict[str, Any], result: RunResult, seconds: float,
          cost: float) -> Score:  # fmt: skip
    products = labels["products"]
    got = outcomes(products, result)
    seeded = labels.get("seeded_errors") or []
    caught = 0
    for s in seeded:
        result_for = got.get(s["product_n"])
        ok = {"asked"} if s["kind"] in MUST_ASK else {"asked", "right"}
        caught += result_for in ok
    values = list(got.values())
    return Score(
        clip=clip,
        seconds_of_video=round(result.ingest.duration_s, 1),
        labelled=len(products),
        found=len(result.products),
        matched=len(match(products, result)),
        with_price=sum(v != "missed" for v in values),
        right=values.count("right"),
        asked=values.count("asked"),
        wrong=values.count("wrong"),
        seeded=len(seeded),
        caught=caught,
        processing_s=round(seconds, 1),
        cost_usd=round(cost, 3),
    )
