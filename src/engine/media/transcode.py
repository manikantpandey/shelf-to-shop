"""Normalise video, extract audio and frames."""

from __future__ import annotations

from pathlib import Path

from engine.media.ffmpeg import DEFAULT_LIMITS, Limits, ffmpeg

MAX_SIDE = 1280
MAX_FPS = 30
ASR_SAMPLE_RATE = 24_000  # Muse Voice Transcribe's native rate (dev.meta.ai/docs/speech-to-text)


def normalise_video(
    src: Path,
    dst: Path,
    *,
    has_audio: bool,
    limits: Limits = DEFAULT_LIMITS,
    clip: tuple[float, float] | None = None,
) -> None:
    """H.264/AAC MP4, longest side <= 1280, <= 30 fps, rotation applied, all metadata dropped.

    `clip` = (start, length) in seconds keeps only that part of a longer video.
    """
    scale = (
        f"scale=w='min({MAX_SIDE},iw)':h='min({MAX_SIDE},ih)'"
        ":force_original_aspect_ratio=decrease:force_divisible_by=2"
    )
    args: list[str | Path] = ["-y"]
    if clip is not None:
        args += ["-ss", f"{max(0.0, clip[0]):.3f}"]
    args += ["-i", src]
    if clip is not None:
        args += ["-t", f"{max(0.1, clip[1]):.3f}"]
    args += ["-map", "0:v:0"]
    args += ["-map", "0:a:0"] if has_audio else ["-an"]
    args += [
        "-vf", scale, "-fpsmax", str(MAX_FPS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        # Phones embed GPS location and device details; none of it should survive.
        "-map_metadata", "-1", "-map_chapters", "-1",
        "-movflags", "+faststart",
    ]  # fmt: skip
    if has_audio:
        args += ["-c:a", "aac", "-b:a", "128k", "-ar", "48000"]
    ffmpeg([*args, dst], limits)


def extract_audio(src: Path, dst: Path, limits: Limits = DEFAULT_LIMITS) -> None:
    """Mono 16-bit PCM WAV at 24 kHz, as Muse Voice Transcribe expects."""
    ffmpeg(
        [
            "-y",
            "-i",
            src,
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(ASR_SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            "-map_metadata",
            "-1",
            "-f",
            "wav",
            dst,
        ],
        limits,
    )


def frame_at(src: Path, t_s: float, dst: Path, limits: Limits = DEFAULT_LIMITS) -> None:
    """One JPEG frame at `t_s` seconds (full normalised resolution)."""
    ffmpeg(
        ["-y", "-ss", f"{max(0.0, t_s):.3f}", "-i", src, "-frames:v", "1", "-q:v", "2", dst],
        limits,
    )


def sample_frames(
    src: Path, out_dir: Path, every_s: float = 1.0, limits: Limits = DEFAULT_LIMITS
) -> list[tuple[float, Path]]:
    """Frames every `every_s` seconds, as (timestamp, path)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / "frame_%04d.jpg"
    ffmpeg(["-y", "-i", src, "-vf", f"fps=1/{every_s}", "-q:v", "3", pattern], limits)
    frames = sorted(out_dir.glob("frame_*.jpg"))
    # The fps filter emits frame n at roughly n * every_s (first at t=0).
    return [(round(i * every_s, 3), path) for i, path in enumerate(frames)]
