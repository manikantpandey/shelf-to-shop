"""Find speech segments in a mono PCM WAV and cut them, for pause-split transcription."""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Segment:
    start_s: float
    end_s: float

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass(frozen=True)
class PauseRules:
    window_s: float = 0.02
    min_silence_s: float = 0.30
    min_speech_s: float = 0.20
    max_segment_s: float = 4.0
    pad_s: float = 0.10
    # Silence: this many dB under the loud (90th percentile) level, or below the absolute floor.
    relative_db: float = 25.0
    floor_dbfs: float = -50.0


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError("expected mono 16-bit PCM WAV")
        rate = wav.getframerate()
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    return samples, rate


def _window_dbfs(samples: np.ndarray, rate: int, window_s: float) -> np.ndarray:
    win = max(1, int(rate * window_s))
    n = len(samples) // win
    if n == 0:
        return np.array([], dtype=float)
    frames = samples[: n * win].astype(np.float64).reshape(n, win) / 32768.0
    rms = np.sqrt(np.mean(frames**2, axis=1))
    return np.asarray(20 * np.log10(np.maximum(rms, 1e-9)))


def speech_segments(
    samples: np.ndarray, rate: int, rules: PauseRules | None = None
) -> list[Segment]:
    rules = rules or PauseRules()
    db = _window_dbfs(samples, rate, rules.window_s)
    if db.size == 0:
        return []
    loud = float(np.percentile(db, 90))
    threshold = max(loud - rules.relative_db, rules.floor_dbfs)
    voiced = db > threshold

    # Runs of voiced windows, with short silences bridged.
    min_gap = int(rules.min_silence_s / rules.window_s)
    runs: list[list[int]] = []
    idx = np.flatnonzero(voiced)
    for i in idx:
        if runs and i - runs[-1][1] <= min_gap:
            runs[-1][1] = int(i)
        else:
            runs.append([int(i), int(i)])

    duration = len(samples) / rate
    segments: list[Segment] = []
    for first, last in runs:
        start = max(0.0, first * rules.window_s - rules.pad_s)
        end = min(duration, (last + 1) * rules.window_s + rules.pad_s)
        if end - start < rules.min_speech_s:
            continue
        # Split long stretches evenly so each piece stays short enough to time words in.
        pieces = max(1, int(np.ceil((end - start) / rules.max_segment_s)))
        step = (end - start) / pieces
        segments += [
            Segment(round(start + k * step, 3), round(start + (k + 1) * step, 3))
            for k in range(pieces)
        ]
    return segments


def cut_wav(samples: np.ndarray, rate: int, segment: Segment) -> bytes:
    a = int(segment.start_s * rate)
    b = int(segment.end_s * rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(samples[a:b].astype("<i2").tobytes())
    return buf.getvalue()
