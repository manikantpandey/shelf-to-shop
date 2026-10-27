"""Spike 3b (offline): combine whole-file transcript text with pause-detected speech timing.

Uses the saved spike 3 responses (no API calls):
D  speech-time interpolation: inside each turn, map character position onto speech time only
   (pauses skipped), instead of the turn's wall-clock span.
E  chunk alignment: split each turn at the ASR's punctuation and align chunks to the speech spans
   inside the turn with a monotonic DP on speaking-rate consistency; time = chunk's span.
Scoring matches each labelled price to the nearest same-value mention in time.

Run: uv run python spikes/03b_align.py
"""

from __future__ import annotations

import json
import re
from typing import Any

from _common import OUT, ROOT, write_json
from engine.media.audio import read_wav, speech_segments
from engine.prices.hinglish import find_prices, likely_prices

CHUNK_SPLIT = re.compile(r"[,，、।.!?;]+")


def score(pred: list[dict[str, Any]], truth: list[dict[str, Any]]) -> dict[str, Any]:
    gts = sorted((p for p in truth if p["spoken_price_inr"]), key=lambda p: p["spoken_at_s"])
    # Global greedy assignment: closest (label, mention) pairs with the same value first.
    pairs = sorted(
        (abs(p["t_s"] - gt["spoken_at_s"]), gi, pi)
        for gi, gt in enumerate(gts)
        for pi, p in enumerate(pred)
        if p["value"] == gt["spoken_price_inr"]
    )
    taken_g: dict[int, int] = {}
    taken_p: set[int] = set()
    for _, gi, pi in pairs:
        if gi not in taken_g and pi not in taken_p:
            taken_g[gi] = pi
            taken_p.add(pi)
    rows = []
    for gi, gt in enumerate(gts):
        row: dict[str, Any] = {
            "n": gt["n"],
            "price": gt["spoken_price_inr"],
            "found": gi in taken_g,
        }
        if gi in taken_g:
            row["err_s"] = round(pred[taken_g[gi]]["t_s"] - gt["spoken_at_s"], 2)
        rows.append(row)
    errs = [abs(r["err_s"]) for r in rows if "err_s" in r]
    return {
        "prices_found": f"{sum(r['found'] for r in rows)}/{len(rows)}",
        "mean_abs_err_s": round(sum(errs) / len(errs), 2) if errs else None,
        "max_abs_err_s": round(max(errs), 2) if errs else None,
        "rows": rows,
    }


def spans_in(spans: list[tuple[float, float]], a: float, b: float) -> list[tuple[float, float]]:
    return [(max(s, a), min(e, b)) for s, e in spans if e > a and s < b]


def speech_time(spans: list[tuple[float, float]], frac: float) -> float:
    total = sum(e - s for s, e in spans)
    target = frac * total
    for s, e in spans:
        if target <= e - s:
            return s + target
        target -= e - s
    return spans[-1][1]


def align(chunks: list[str], spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Monotonic alignment: each chunk gets a contiguous run of spans (or shares one span)."""
    n, m = len(chunks), len(spans)
    lens = [max(1, len(c.strip())) for c in chunks]
    rate = sum(lens) / max(1e-6, sum(e - s for s, e in spans))  # chars per second overall
    inf = float("inf")
    # cost[i][j]: best cost aligning first i chunks to first j spans.
    cost = [[inf] * (m + 1) for _ in range(n + 1)]
    back: list[list[tuple[int, int] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            if cost[i][j] == inf:
                continue
            # Next chunk takes the next 1-2 spans; or two chunks share one span.
            for take in (1, 2):
                if i < n and j + take <= m:
                    dur = spans[j + take - 1][1] - spans[j][0]
                    c = cost[i][j] + abs(lens[i] / rate - dur)
                    if c < cost[i + 1][j + take]:
                        cost[i + 1][j + take], back[i + 1][j + take] = c, (i, j)
            if i + 2 <= n and j < m:
                dur = spans[j][1] - spans[j][0]
                c = cost[i][j] + abs((lens[i] + lens[i + 1]) / rate - dur) + 0.3
                if c < cost[i + 2][j + 1]:
                    cost[i + 2][j + 1], back[i + 2][j + 1] = c, (i, j)
    if cost[n][m] == inf:
        return []
    out: list[tuple[float, float]] = [(0.0, 0.0)] * n
    i, j = n, m
    while (i, j) != (0, 0):
        prev = back[i][j]
        assert prev is not None
        pi, pj = prev
        for k in range(pi, i):
            out[k] = (spans[pj][0], spans[j - 1][1])
        i, j = pi, pj
    return out


def main() -> None:
    rep = json.loads((OUT / "03" / "synth_a_report.json").read_text(encoding="utf-8"))
    truth = json.loads((ROOT / "evals" / "labels" / "synth_a.json").read_text(encoding="utf-8"))
    samples, rate = read_wav(OUT / "01" / "synth_a" / "ingest" / "audio_24k.wav")
    spans = [(s.start_s, s.end_s) for s in speech_segments(samples, rate)]
    turns = [(a / 1000, b / 1000, text) for a, b, text in rep["A_endpointing"]["turns"]]

    pred_a, pred_d, pred_e = [], [], []
    for a, b, text in turns:
        inside = spans_in(spans, a, b) or [(a, b)]
        n = max(1, len(text))
        for m in likely_prices(find_prices(text)):
            pred_a.append({"value": m.value, "t_s": a + (b - a) * m.start / n})
            pred_d.append({"value": m.value, "t_s": speech_time(inside, m.start / n)})
        chunks = [c for c in CHUNK_SPLIT.split(text) if c.strip()]
        for chunk, (s, _e) in zip(chunks, align(chunks, inside), strict=False):
            for m in likely_prices(find_prices(chunk)):
                pred_e.append({"value": m.value, "t_s": s})

    report = {
        "A_turn_interpolation": score(pred_a, truth["products"]),
        "D_speech_time_interpolation": score(pred_d, truth["products"]),
        "E_chunk_span_alignment": score(pred_e, truth["products"]),
    }
    for k, v in report.items():
        print(k, {x: y for x, y in v.items() if x != "rows"})
        for row in v["rows"]:
            print("   ", row)
    write_json(OUT / "03" / "synth_a_alignment.json", report)


if __name__ == "__main__":
    main()
