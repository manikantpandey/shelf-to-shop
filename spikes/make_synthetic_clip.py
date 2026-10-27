"""Build a synthetic shelf walkthrough with exact ground truth, for spikes before real clips exist.

Muse Image draws six saree photos; ffmpeg pans across each and cross-fades between them; Windows
neural TTS (Indian English voice) speaks Hinglish descriptions and prices at known times. The clip
seeds the hard cases from SHOOTING.md: tag/spoken conflict, price said before and after the item,
two blue sarees, Hindi number words, one item with no price.

Run:   uv run python spikes/make_synthetic_clip.py
Output: evals/videos/synth_a.mp4 (gitignored) and evals/labels/synth_a.json.
This is a proxy only; real seller clips remain the test that counts.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from _common import ROOT, load_env, meta_base_url, model_id, require
from engine.media.audio import read_wav, speech_segments
from engine.media.ffmpeg import ffmpeg
from engine.providers.meta_client import MetaClient

WORK = ROOT / "spikes" / "media" / "synth_a"
VIDEO_OUT = ROOT / "evals" / "videos" / "synth_a.mp4"
LABELS_OUT = ROOT / "evals" / "labels" / "synth_a.json"
# Seconds each product is on screen (cross-fades overlap neighbours by FADE_S).
LENGTHS = [5.0, 7.0, 5.0, 5.0, 5.0, 7.5]
FADE_S = 0.5
RATE = 16_000

# description, image prompt, narration (desc, price words or None), narration start (s), whether
# the price is said before the description, spoken price, tag price visible near the item, notes.
PRODUCTS: list[dict[str, Any]] = [
    {"what": "blue cotton saree, thin gold border",
     "image": "a folded blue cotton saree with a thin gold border",
     "say": ("ye neela wala", "barah sau"), "at": 1.0, "price": 1200, "tag": None, "notes": ""},
    {"what": "red silk saree, wide gold zari border, paper tag 1100",
     "image": "a folded red silk saree with a wide gold zari border, with a small handwritten "
              "paper price tag that clearly reads 'Rs 1100' pinned on the fabric",
     "say": ("ye laal silk wali", "ek hazaar do sau"), "at": 5.4, "price": 1200, "tag": 1100,
     "notes": "tag reads Rs 1100"},
    {"what": "green cotton saree (price said before it appears)",
     "image": "a folded plain green cotton saree",
     "say": ("agla hara wala", "saadhe aath sau"), "at": 9.2, "price_first": True, "price": 850,
     "tag": None, "notes": "whole price said while item 2 is still on screen"},
    {"what": "light blue cotton saree (second blue item)",
     "image": "a folded light sky-blue cotton saree with small white flowers",
     "say": ("ye bhi neela, halka wala", "nau sau"), "at": 16.2, "price": 900, "tag": None,
     "notes": "image shows loose white flowers on the fabric"},
    {"what": "yellow silk saree (price said after moving past)",
     "image": "a folded bright yellow silk saree with a maroon border",
     "say": ("peeche wala peela", "dedh hazaar"), "at": 25.3, "price": 1500, "tag": None,
     "notes": "said after item left the screen; background sign 'Cotton 550' is a distractor"},
    {"what": "pink chiffon saree (no price said)",
     "image": "a folded pink chiffon saree",
     "say": ("aur ye gulabi wala bhi dekh lijiye", None), "at": 28.5, "price": None, "tag": 1250,
     "notes": "no price said; printed shelf label 'Pink Chiffon 1250' bottom right"},
]  # fmt: skip


def windows() -> list[tuple[float, float]]:
    spans = []
    start = 0.0
    for length in LENGTHS:
        spans.append((round(start, 3), round(start + length, 3)))
        start += length - FADE_S
    return spans


async def make_images() -> list[Path]:
    WORK.mkdir(parents=True, exist_ok=True)
    paths = [WORK / f"product_{i + 1}.png" for i in range(len(PRODUCTS))]
    todo = [(p, prod) for p, prod in zip(paths, PRODUCTS, strict=True) if not p.exists()]
    if todo:
        async with MetaClient(require("META_API_KEY"), meta_base_url(), timeout_s=180) as client:
            model = model_id("META_IMAGE_MODEL", "muse-image-1.0")

            async def one(path: Path, prod: dict[str, Any]) -> None:
                prompt = (
                    f"Phone photo, close up, of {prod['image']} lying on a wooden shelf in a small "
                    "Indian saree shop, natural light, other folded fabric slightly visible at the "
                    "edges, no people"
                )
                path.write_bytes(await client.generate_image(model, prompt, size="1536x1024"))

            await asyncio.gather(*(one(p, prod) for p, prod in todo))
    return paths


def make_tts() -> dict[str, Path]:
    phrases = []
    for i, prod in enumerate(PRODUCTS, 1):
        desc, price = prod["say"]
        phrases.append({"id": f"p{i}_desc", "text": desc})
        if price:
            phrases.append({"id": f"p{i}_price", "text": price})
    tts_dir = WORK / "tts"
    spec = WORK / "phrases.json"
    spec.write_text(json.dumps(phrases, ensure_ascii=False), encoding="utf-8")
    if not all((tts_dir / f"{p['id']}.wav").exists() for p in phrases):
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-File",
                str(ROOT / "spikes" / "tts_windows.ps1"),
                "-PhrasesJson",
                str(spec),
                "-OutDir",
                str(tts_dir),
            ],  # fmt: skip
            check=True,
        )
    return {p["id"]: tts_dir / f"{p['id']}.wav" for p in phrases}


def trimmed(path: Path) -> np.ndarray:
    samples, rate = read_wav(path)
    assert rate == RATE, f"expected {RATE} Hz TTS, got {rate}"
    segs = speech_segments(samples, rate)
    return samples[int(segs[0].start_s * rate) : int(segs[-1].end_s * rate)]


def make_audio(tts: dict[str, Path], total_s: float) -> tuple[Path, list[dict[str, float]]]:
    rng = np.random.default_rng(7)
    track = rng.normal(0, 60, int(total_s * RATE))  # quiet shop noise, about -55 dBFS
    timings = []
    for i, prod in enumerate(PRODUCTS, 1):
        at = prod["at"]
        gap = int(0.15 * RATE)
        pieces = [("desc", trimmed(tts[f"p{i}_desc"]))]
        if f"p{i}_price" in tts:
            price_piece = ("price", trimmed(tts[f"p{i}_price"]))
            pieces = [price_piece, *pieces] if prod.get("price_first") else [*pieces, price_piece]
        entry = {"phrase_start_s": at, "price_start_s": -1.0, "price_end_s": -1.0}
        cursor = int(at * RATE)
        for kind, clip in pieces:
            track[cursor : cursor + len(clip)] += clip
            if kind == "price":
                entry["price_start_s"] = round(cursor / RATE, 3)
                entry["price_end_s"] = round((cursor + len(clip)) / RATE, 3)
            cursor += len(clip) + gap
        timings.append(entry)
    out = WORK / "narration.wav"
    import wave

    with wave.open(str(out), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(np.clip(track, -32768, 32767).astype("<i2").tobytes())
    return out, timings


def make_video(images: list[Path], audio: Path, total_s: float) -> None:
    segs = []
    for i, (img, length) in enumerate(zip(images, LENGTHS, strict=True)):
        Image.open(img).convert("RGB").save(WORK / f"product_{i + 1}.jpg", quality=92)
        seg = WORK / f"seg_{i + 1}.mp4"
        # Slow horizontal pan across a 1600-wide scale, as if walking past the shelf.
        pan = f"scale=1600:-2,crop=1280:720:'(iw-1280)*t/{length}':'(ih-720)/2'"
        ffmpeg([
            "-y", "-loop", "1", "-t", str(length), "-i", WORK / f"product_{i + 1}.jpg",
            "-vf", f"{pan},fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
            seg,
        ])  # fmt: skip
        segs.append(seg)
    inputs: list[str | Path] = []
    for seg in segs:
        inputs += ["-i", seg]
    chain, label, offset = [], "0:v", 0.0
    for i in range(1, len(segs)):
        offset += LENGTHS[i - 1] - FADE_S
        out = f"v{i}"
        chain.append(
            f"[{label}][{i}:v]xfade=transition=fade:duration={FADE_S}:offset={offset}[{out}]"
        )
        label = out
    VIDEO_OUT.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg([
        "-y", *inputs, "-i", audio, "-filter_complex", ";".join(chain),
        "-map", f"[{label}]", "-map", f"{len(segs)}:a", "-c:v", "libx264", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "96k", "-t", str(total_s), VIDEO_OUT,
    ])  # fmt: skip


def main() -> None:
    load_env()
    spans = windows()
    total_s = spans[-1][1]
    images = asyncio.run(make_images())
    tts = make_tts()
    audio, timings = make_audio(tts, total_s)
    make_video(images, audio, total_s)
    labels = {
        "video": VIDEO_OUT.name,
        "consent": "synthetic: Muse Image products, Windows TTS narration, no people",
        "language_notes": "Hinglish narration by an Indian English TTS voice",
        "products": [
            {
                "n": i,
                "what": prod["what"],
                "appears_s": list(spans[i - 1]),
                "spoken_price_inr": prod["price"],
                "spoken_at_s": timings[i - 1]["price_start_s"]
                if timings[i - 1]["price_start_s"] >= 0
                else None,
                "spoken_end_s": timings[i - 1]["price_end_s"]
                if timings[i - 1]["price_end_s"] >= 0
                else None,
                "spoken_words": " ".join(w for w in prod["say"] if w),
                "tag_price_inr": prod["tag"],
                "notes": prod["notes"],
            }
            for i, prod in enumerate(PRODUCTS, 1)
        ],
        "seeded_errors": [
            {"kind": "price_conflict", "product_n": 2, "notes": "tag 1100 vs spoken 1200"},
            {"kind": "price_before_item", "product_n": 3, "notes": "said while item 2 on screen"},
            {"kind": "same_colour", "product_n": 4, "notes": "second blue saree"},
            {"kind": "price_after_item", "product_n": 5, "notes": "said while item 6 on screen"},
            {"kind": "missing_price", "product_n": 6, "notes": "no price said (tag 1250 visible)"},
        ],
    }
    LABELS_OUT.write_text(json.dumps(labels, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {VIDEO_OUT} ({VIDEO_OUT.stat().st_size // 1024} KB) and {LABELS_OUT}")


if __name__ == "__main__":
    main()
