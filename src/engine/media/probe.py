"""Content sniffing and ffprobe validation, done before any processing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.media.ffmpeg import (
    DEFAULT_LIMITS,
    Limits,
    MediaToolError,
    ffprobe_json,
    ffprobe_packet_end,
)


class MediaRejectedError(ValueError):
    """The file is not a video we accept. `code` is stable and maps to a user-facing message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class MediaRules:
    max_duration_s: float = 75.0
    min_duration_s: float = 2.0
    max_bytes: int = 200 * 1024**2
    min_short_side: int = 240
    max_long_side: int = 4096


@dataclass(frozen=True)
class ProbeResult:
    container: str
    duration_s: float
    width: int  # as displayed (rotation applied)
    height: int
    fps: float
    video_codec: str
    has_audio: bool
    audio_codec: str | None
    size_bytes: int


def sniff_container(head: bytes) -> str | None:
    """Recognise the containers phones record: ISO BMFF (mp4/mov/3gp) and EBML (webm/mkv)."""
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "isobmff"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "ebml"
    return None


def _fps(stream: dict[str, Any]) -> float:
    for key in ("avg_frame_rate", "r_frame_rate"):
        num, _, den = str(stream.get(key, "0/1")).partition("/")
        try:
            value = float(num) / float(den or 1)
        except (ValueError, ZeroDivisionError):
            continue
        if value > 0:
            return value
    return 0.0


def _rotation(stream: dict[str, Any]) -> int:
    rotate = stream.get("tags", {}).get("rotate")
    if rotate is not None:
        return int(float(rotate)) % 360
    for side in stream.get("side_data_list", []):
        if "rotation" in side:
            return int(float(side["rotation"])) % 360
    return 0


def probe(
    path: Path, rules: MediaRules | None = None, limits: Limits = DEFAULT_LIMITS
) -> ProbeResult:
    rules = rules or MediaRules()
    size = path.stat().st_size
    if size > rules.max_bytes:
        raise MediaRejectedError(
            "too_large", f"video is {size // 1024**2} MB; limit is {rules.max_bytes // 1024**2} MB"
        )
    with path.open("rb") as fh:
        container = sniff_container(fh.read(16))
    if container is None:
        raise MediaRejectedError("not_a_video", "file is not an MP4, MOV or WebM video")
    try:
        info = json.loads(ffprobe_json(path, limits))
    except (MediaToolError, json.JSONDecodeError) as exc:
        raise MediaRejectedError("unreadable", "video could not be read") from exc

    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if video is None:
        raise MediaRejectedError("no_video_stream", "file has no video track")
    duration = float(info.get("format", {}).get("duration") or video.get("duration") or 0)
    if duration <= 0:
        # Recorded in a browser: no duration in the header, so measure it from the packets.
        try:
            duration = ffprobe_packet_end(path, limits)
        except MediaToolError as exc:
            raise MediaRejectedError("unreadable", "video could not be read") from exc
    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    if _rotation(video) in (90, 270):
        width, height = height, width
    if duration < rules.min_duration_s:
        raise MediaRejectedError(
            "too_short", f"video is {duration:.1f}s; record at least {rules.min_duration_s:.0f}s"
        )
    if duration > rules.max_duration_s:
        raise MediaRejectedError(
            "too_long", f"video is {duration:.0f}s; limit is {rules.max_duration_s:.0f}s"
        )
    if min(width, height) < rules.min_short_side or max(width, height) > rules.max_long_side:
        raise MediaRejectedError("bad_resolution", f"unsupported resolution {width}x{height}")
    return ProbeResult(
        container=container,
        duration_s=duration,
        width=width,
        height=height,
        fps=_fps(video),
        video_codec=str(video.get("codec_name", "")),
        has_audio=audio is not None,
        audio_codec=str(audio.get("codec_name")) if audio else None,
        size_bytes=size,
    )
