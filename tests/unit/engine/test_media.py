from __future__ import annotations

import json
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from engine.media.audio import PauseRules, cut_wav, read_wav, speech_segments
from engine.media.ffmpeg import ffprobe_json
from engine.media.ingest import ingest
from engine.media.probe import MediaRejectedError, MediaRules, probe, sniff_container

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg not installed"
)


def make_clip(
    path: Path,
    *,
    size: str = "1920x1080",
    rate: int = 30,
    seconds: float = 3,
    audio: bool = True,
    vcodec: str = "libx264",
    acodec: str = "aac",
    extra: list[str] | None = None,
) -> Path:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}"]  # fmt: skip
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]
    cmd += ["-t", str(seconds), "-c:v", vcodec, *(["-c:a", acodec] if audio else [])]
    cmd += [*(extra or []), str(path)]
    subprocess.run(cmd, check=True)  # noqa: S603
    return path


def streams(path: Path) -> dict[str, dict[str, object]]:
    info = json.loads(ffprobe_json(path))
    return {s["codec_type"]: s for s in info["streams"]} | {"format": info["format"]}


def test_sniff_container() -> None:
    assert sniff_container(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00") == "isobmff"
    assert sniff_container(b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81") == "ebml"
    assert sniff_container(b"#!/bin/sh\nrm -rf /") is None


@needs_ffmpeg
def test_landscape_clip_is_normalised_and_metadata_stripped(tmp_path: Path) -> None:
    src = make_clip(
        tmp_path / "src.mp4",
        rate=60,
        extra=["-metadata", "location=+12.9716+077.5946/", "-metadata", "title=secret"],
    )
    result = ingest(src, tmp_path / "work")
    assert (result.width, result.height) == (1280, 720)
    assert result.fps <= 30.5
    out = streams(result.video)
    assert out["video"]["codec_name"] == "h264"
    assert out["audio"]["codec_name"] == "aac"
    tags = {k.lower() for k in out["format"].get("tags", {})}  # type: ignore[union-attr]
    assert "location" not in tags
    assert "title" not in tags
    assert result.audio is not None
    with wave.open(str(result.audio)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 24000)
    assert len(result.frames) >= 3
    assert result.frames[0].path.read_bytes()[:2] == b"\xff\xd8"  # JPEG


@needs_ffmpeg
def test_portrait_clip_keeps_orientation(tmp_path: Path) -> None:
    src = make_clip(tmp_path / "p.mp4", size="1080x1920")
    result = ingest(src, tmp_path / "work")
    assert (result.width, result.height) == (720, 1280)


@needs_ffmpeg
def test_android_webm_is_transcoded_to_h264(tmp_path: Path) -> None:
    src = make_clip(tmp_path / "a.webm", size="640x480", vcodec="libvpx", acodec="libopus")
    result = ingest(src, tmp_path / "work")
    assert result.source_container == "ebml"
    assert result.source_codec == "vp8"
    assert streams(result.video)["video"]["codec_name"] == "h264"
    assert (result.width, result.height) == (640, 480)


@needs_ffmpeg
def test_clip_without_audio(tmp_path: Path) -> None:
    result = ingest(make_clip(tmp_path / "s.mp4", audio=False), tmp_path / "work")
    assert result.audio is None
    assert result.speech == []


@needs_ffmpeg
@pytest.mark.parametrize(
    ("make", "rules", "code"),
    [
        ("text", MediaRules(), "not_a_video"),
        ("short", MediaRules(), "too_short"),
        ("long", MediaRules(max_duration_s=2), "too_long"),
        ("tiny", MediaRules(), "bad_resolution"),
        ("big", MediaRules(max_bytes=1000), "too_large"),
    ],
)
def test_rejections(tmp_path: Path, make: str, rules: MediaRules, code: str) -> None:
    path = tmp_path / "x.mp4"
    if make == "text":
        path.write_text("definitely not a video " * 50)
    elif make == "short":
        make_clip(path, seconds=1)
    elif make == "tiny":
        make_clip(path, size="160x120")
    else:
        make_clip(path)
    with pytest.raises(MediaRejectedError) as exc:
        probe(path, rules)
    assert exc.value.code == code


def _tone(seconds: float, rate: int = 24000, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(seconds * rate)) / rate
    return (amp * 32767 * np.sin(2 * np.pi * 220 * t)).astype("<i2")


def _silence(seconds: float, rate: int = 24000) -> np.ndarray:
    rng = np.random.default_rng(0)
    return (rng.normal(0, 20, int(seconds * rate))).astype("<i2")


def test_speech_segments_split_on_pauses() -> None:
    samples = np.concatenate([_silence(0.5), _tone(1.0), _silence(0.7), _tone(0.8), _silence(0.5)])
    segs = speech_segments(samples, 24000)
    assert len(segs) == 2
    assert abs(segs[0].start_s - 0.4) < 0.1
    assert abs(segs[0].end_s - 1.6) < 0.1
    assert abs(segs[1].start_s - 2.1) < 0.1


def test_short_pauses_are_bridged_and_long_speech_is_chunked() -> None:
    samples = np.concatenate([_tone(2.0), _silence(0.1), _tone(7.0)])
    segs = speech_segments(samples, 24000, PauseRules(max_segment_s=4.0))
    assert len(segs) == 3
    assert all(s.duration_s <= 4.0 + 1e-6 for s in segs)
    assert segs[0].start_s == 0.0


def test_cut_wav_round_trip(tmp_path: Path) -> None:
    samples = np.concatenate([_silence(0.5), _tone(1.0)])
    seg = speech_segments(samples, 24000)[0]
    data = cut_wav(samples, 24000, seg)
    path = tmp_path / "seg.wav"
    path.write_bytes(data)
    cut, rate = read_wav(path)
    assert rate == 24000
    assert abs(len(cut) / rate - seg.duration_s) < 0.01
