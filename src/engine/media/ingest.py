"""Ingest: validate an uploaded video and produce the normalised inputs later stages use."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from pydantic import BaseModel

from engine.media.audio import PauseRules, read_wav, speech_segments
from engine.media.ffmpeg import DEFAULT_LIMITS, Limits
from engine.media.probe import LONG_UPLOAD_S, MediaRules, ProbeResult, probe
from engine.media.transcode import extract_audio, normalise_video, sample_frames


class Frame(BaseModel):
    t_s: float
    path: Path


class SpeechSpan(BaseModel):
    start_s: float
    end_s: float


class IngestResult(BaseModel):
    source_container: str
    source_codec: str
    duration_s: float
    width: int
    height: int
    fps: float
    video: Path
    audio: Path | None
    frames: list[Frame]
    speech: list[SpeechSpan]


def ingest(
    src: Path,
    work_dir: Path,
    *,
    rules: MediaRules | None = None,
    limits: Limits = DEFAULT_LIMITS,
    frame_every_s: float = 1.0,
    pauses: PauseRules | None = None,
    clip: tuple[float, float] | None = None,
) -> IngestResult:
    """`clip` = (start, length): use only that part of a longer upload (the seller picked it)."""
    rules = rules or MediaRules()
    work_dir.mkdir(parents=True, exist_ok=True)
    long_ok = replace(rules, max_duration_s=max(rules.max_duration_s, LONG_UPLOAD_S))
    source: ProbeResult = probe(src, rules if clip is None else long_ok, limits)

    video = work_dir / "video_720p.mp4"
    normalise_video(src, video, has_audio=source.has_audio, limits=limits, clip=clip)
    out: ProbeResult = probe(video, rules, limits)

    audio: Path | None = None
    speech: list[SpeechSpan] = []
    if out.has_audio:
        audio = work_dir / "audio_24k.wav"
        extract_audio(video, audio, limits)
        samples, rate = read_wav(audio)
        speech = [
            SpeechSpan(start_s=s.start_s, end_s=s.end_s)
            for s in speech_segments(samples, rate, pauses)
        ]

    frames = [
        Frame(t_s=t, path=p)
        for t, p in sample_frames(video, work_dir / "frames", frame_every_s, limits)
    ]
    return IngestResult(
        source_container=source.container,
        source_codec=source.video_codec,
        duration_s=out.duration_s,
        width=out.width,
        height=out.height,
        fps=out.fps,
        video=video,
        audio=audio,
        frames=frames,
        speech=speech,
    )
