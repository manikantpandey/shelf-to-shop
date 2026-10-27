"""Put whole-file transcript text on the audio timeline.

Muse Voice Transcribe gives turn-level times only, and turns can run 10-15 s. Transcribing short
pause-split pieces gives exact times but loses context (spike 3). So: keep the whole-file text,
split each turn at the punctuation the ASR puts at pauses, and align those chunks to the speech
spans our pause detector found inside the turn (monotonic DP on speaking-rate consistency).
"""

from __future__ import annotations

import re
from typing import Literal

from engine.pipeline.schemas import TimedChunk, TimedMention
from engine.prices.hinglish import find_prices, likely_prices

# ASR output mixes scripts, so split on Latin, fullwidth, CJK and Devanagari (danda) punctuation.
SPECIAL_TOKEN = re.compile(r"<\|[^|>]{0,40}\|>")  # e.g. <|speaker_A|> leaking into text
CHUNK_SPLIT = re.compile(r"[,，、。।.!?;:]+")  # noqa: RUF001
Span = tuple[float, float]


def spans_within(spans: list[Span], start: float, end: float) -> list[Span]:
    return [(max(s, start), min(e, end)) for s, e in spans if e > start and s < end]


def align_chunks(chunks: list[str], spans: list[Span]) -> list[Span] | None:
    """Give each chunk a time range made of whole spans. None if no consistent alignment."""
    n, m = len(chunks), len(spans)
    if n == 0 or m == 0:
        return None
    lens = [max(1, len(c.strip())) for c in chunks]
    speech = sum(e - s for s, e in spans)
    rate = sum(lens) / max(1e-6, speech)  # characters per second of speech
    inf = float("inf")
    cost = [[inf] * (m + 1) for _ in range(n + 1)]
    back: list[list[tuple[int, int] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            here = cost[i][j]
            if here == inf:
                continue
            # One chunk over one or two spans (a mid-chunk breath), or two chunks sharing a span.
            for take in (1, 2):
                if i < n and j + take <= m:
                    dur = spans[j + take - 1][1] - spans[j][0]
                    c = here + abs(lens[i] / rate - dur) + (0.2 if take == 2 else 0.0)
                    if c < cost[i + 1][j + take]:
                        cost[i + 1][j + take], back[i + 1][j + take] = c, (i, j)
            if i + 2 <= n and j < m:
                dur = spans[j][1] - spans[j][0]
                c = here + abs((lens[i] + lens[i + 1]) / rate - dur) + 0.3
                if c < cost[i + 2][j + 1]:
                    cost[i + 2][j + 1], back[i + 2][j + 1] = c, (i, j)
    if cost[n][m] == inf:
        return None
    out: list[Span] = [(0.0, 0.0)] * n
    i, j = n, m
    while (i, j) != (0, 0):
        prev = back[i][j]
        if prev is None:
            return None
        pi, pj = prev
        for k in range(pi, i):
            out[k] = (spans[pj][0], spans[j - 1][1])
        i, j = pi, pj
    return out


def _speech_time(spans: list[Span], frac: float) -> float:
    """Map a 0..1 fraction of the text onto speech time, skipping pauses."""
    total = sum(e - s for s, e in spans)
    target = frac * total
    for s, e in spans:
        if target <= e - s:
            return s + target
        target -= e - s
    return spans[-1][1]


def place_turns(
    turns: list[tuple[float, float, str]], speech_spans: list[Span]
) -> tuple[list[TimedChunk], list[TimedMention], Literal["aligned", "interpolated", "none"]]:
    """Chunks and price mentions with times. Returns (chunks, mentions, timing method)."""
    chunks: list[TimedChunk] = []
    methods: set[str] = set()
    for turn_no, (start, end, text) in enumerate(turns):
        inside = spans_within(speech_spans, start, end) or [(start, end)]
        text = SPECIAL_TOKEN.sub(" ", text)
        pieces = [p for p in CHUNK_SPLIT.split(text) if p.strip()]
        aligned = align_chunks(pieces, inside)
        if aligned is not None:
            methods.add("aligned")
            placed = list(zip(pieces, aligned, strict=True))
        else:
            # Fall back to spreading the text over speech time inside the turn.
            methods.add("interpolated")
            total = max(1, sum(len(p) for p in pieces))
            placed, seen = [], 0
            for p in pieces:
                a = _speech_time(inside, seen / total)
                seen += len(p)
                placed.append((p, (a, _speech_time(inside, seen / total))))
        for raw, (s, e) in placed:
            chunks.append(TimedChunk(start_s=round(s, 3), end_s=round(e, 3), text=raw.strip(),
                                     turn=turn_no))  # fmt: skip
    mentions = mentions_in_chunks(chunks)
    if methods == {"aligned"}:
        return chunks, mentions, "aligned"
    return chunks, mentions, "interpolated" if methods else "none"


def mentions_in_chunks(chunks: list[TimedChunk]) -> list[TimedMention]:
    """Price mentions with times, read from already-placed chunks.

    Kept separate from transcription so parser improvements apply to cached transcripts.
    """
    mentions: list[TimedMention] = []
    for chunk_idx, chunk in enumerate(chunks):
        s, e, piece = chunk.start_s, chunk.end_s, chunk.text
        for m in likely_prices(find_prices(piece)):
            frac = m.start / max(1, len(piece))
            mentions.append(
                TimedMention(
                    value_inr=m.value,
                    t_s=round(s + (e - s) * frac, 3),
                    words=m.text,
                    chunk=chunk_idx,
                    confidence=m.confidence,
                )
            )
    return mentions
