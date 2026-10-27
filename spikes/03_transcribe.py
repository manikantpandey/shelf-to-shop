"""Spike 3: are spoken prices and their times reliable from Muse Voice Transcribe?

A  whole file, ENDPOINTING JSON: turn times, word time interpolated by character position
B  pause-split: each detected speech segment transcribed alone, then interpolated inside it
C  whole file, ENDPOINTING event stream: time a price first appears in the partial transcripts
Prices are read from the transcripts with engine.prices.hinglish and scored against the labels.

Run after spike 1 (it reuses the ingested audio): uv run python spikes/03_transcribe.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
from decimal import Decimal
from typing import Any

import httpx

from _common import (
    OUT,
    ROOT,
    Timer,
    describe_error,
    load_env,
    meta_base_url,
    meta_headers,
    write_json,
)
from engine.media.audio import Segment, cut_wav, read_wav, speech_segments
from engine.prices.hinglish import find_prices, likely_prices
from engine.spend import transcribe_cost

MODEL = "muse-voice-transcribe-1.0"
BIAS = {"languageBias": ["Hindi", "English"]}


def request(mode: str, **extra: Any) -> dict[str, Any]:
    return {"model": MODEL, "audioEncoding": "WAV", "mode": mode, **BIAS, **extra}


async def transcribe(
    client: httpx.AsyncClient, wav: bytes, req: dict[str, Any], accept: str = "application/json"
) -> httpx.Response:
    files = {
        "request": (None, json.dumps(req), "application/json"),
        "audio": ("audio.wav", wav, "audio/wav"),
    }
    r = await client.post("/asr/transcribe", files=files, headers={"Accept": accept})
    if r.status_code != 200:
        raise RuntimeError(describe_error(r))
    return r


def mentions_in(text: str, start_s: float, end_s: float) -> list[dict[str, Any]]:
    """Price mentions with a time interpolated by character position inside [start, end]."""
    out = []
    n = max(1, len(text))
    for m in likely_prices(find_prices(text)):
        t = start_s + (end_s - start_s) * (m.start / n)
        out.append({"value": m.value, "t_s": round(t, 2), "words": m.text})
    return out


def score(pred: list[dict[str, Any]], truth: list[dict[str, Any]], key: str) -> dict[str, Any]:
    gts = sorted((p for p in truth if p["spoken_price_inr"]), key=lambda p: p["spoken_at_s"])
    pool = sorted(pred, key=lambda p: p["t_s"])
    used: set[int] = set()
    rows = []
    for gt in gts:
        hit = next((i for i, p in enumerate(pool)
                    if i not in used and p["value"] == gt["spoken_price_inr"]), None)  # fmt: skip
        row: dict[str, Any] = {
            "n": gt["n"],
            "price": gt["spoken_price_inr"],
            "found": hit is not None,
        }
        if hit is not None:
            used.add(hit)
            row["err_s"] = round(pool[hit]["t_s"] - gt[key], 2)
        rows.append(row)
    errs = [abs(r["err_s"]) for r in rows if "err_s" in r]
    return {
        "prices_found": f"{sum(r['found'] for r in rows)}/{len(rows)}",
        "extra_mentions": len(pool) - len(used),
        "mean_abs_err_s": round(sum(errs) / len(errs), 2) if errs else None,
        "max_abs_err_s": round(max(errs), 2) if errs else None,
        "rows": rows,
    }


async def run(clip: str) -> None:
    load_env()
    audio = OUT / "01" / clip / "ingest" / "audio_24k.wav"
    truth = json.loads((ROOT / "evals" / "labels" / f"{clip}.json").read_text(encoding="utf-8"))
    wav = audio.read_bytes()
    samples, rate = read_wav(audio)
    duration = len(samples) / rate
    report: dict[str, Any] = {"clip": clip, "duration_s": round(duration, 1)}

    async with httpx.AsyncClient(
        base_url=meta_base_url(), headers=meta_headers(), timeout=300
    ) as c:
        # A: one call, turn timestamps.
        with Timer() as t:
            body = (await transcribe(c, wav, request("ENDPOINTING"))).json()
        pred_a = []
        for turn in body.get("turns", []):
            pred_a += mentions_in(turn["transcript"], turn["startMs"] / 1000, turn["endMs"] / 1000)
        report["A_endpointing"] = {
            "latency_ms": t.ms,
            "transcript": body.get("transcript"),
            "turns": [
                (tn["startMs"], tn["endMs"], tn["transcript"]) for tn in body.get("turns", [])
            ],
            "score": score(pred_a, truth["products"], "spoken_at_s"),
        }

        # B: pause-split segments, transcribed concurrently.
        segments = speech_segments(samples, rate)
        sem = asyncio.Semaphore(6)

        async def one(seg: Segment) -> tuple[Segment, str]:
            async with sem:
                r = await transcribe(c, cut_wav(samples, rate, seg), request("PUSH_TO_TALK"))
            return seg, r.json().get("transcript", "")

        with Timer() as t:
            parts = await asyncio.gather(*(one(s) for s in segments))
        pred_b = []
        for seg, text in parts:
            pred_b += mentions_in(text, seg.start_s, seg.end_s)
        report["B_pause_split"] = {
            "latency_ms": t.ms,
            "segments": [(s.start_s, s.end_s, text) for s, text in parts],
            "score": score(pred_b, truth["products"], "spoken_at_s"),
        }

        # C: streamed partials; a price's time = first audioProcessedMs where it shows up.
        with Timer() as t:
            r = await transcribe(c, wav, request("ENDPOINTING", partialMode="CUMULATIVE"),
                                 accept="text/event-stream")  # fmt: skip
        seen: dict[tuple[int, int], float] = {}
        events = 0
        for line in r.text.splitlines():
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:])
            except json.JSONDecodeError:
                continue
            events += 1
            if ev.get("type") not in ("transcript", "speechComplete"):
                continue
            at = ev.get("audioProcessedMs", 0) / 1000
            for k, m in enumerate(likely_prices(find_prices(ev.get("transcript", "")))):
                seen.setdefault(
                    (ev.get("turnId", 0) if ev.get("type") == "speechComplete" else -1, k), at
                )
                seen.setdefault((m.value, k), at)
        pred_c = [
            {"value": value, "t_s": round(at, 2)} for (value, _k), at in seen.items() if value > 10
        ]
        report["C_partials"] = {
            "latency_ms": t.ms,
            "events": events,
            "score_vs_price_end": score(pred_c, truth["products"], "spoken_end_s"),
        }

    report["cost_usd_est"] = str(
        transcribe_cost(duration) * 2
        + sum((transcribe_cost(s.duration_s) for s in segments), Decimal(0))
    )
    for key in ("A_endpointing", "B_pause_split", "C_partials"):
        sc = report[key].get("score") or report[key]["score_vs_price_end"]
        print(key, f"{report[key]['latency_ms']} ms", {k: v for k, v in sc.items() if k != "rows"})
        for row in sc["rows"]:
            print("   ", row)
    print("A transcript:", report["A_endpointing"]["transcript"])
    write_json(OUT / "03" / f"{clip}_report.json", report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clip", default="synth_a")
    asyncio.run(run(parser.parse_args().clip))
