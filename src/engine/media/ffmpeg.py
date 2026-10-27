"""Run ffmpeg/ffprobe safely: no shell, no network protocols, wall-clock timeout, POSIX rlimits.

All paths passed here are created by us (random names in a job work directory), never taken from
user input.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path


class MediaToolError(RuntimeError):
    """ffmpeg/ffprobe failed or is missing. `detail` holds the tool's (truncated) stderr."""

    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.detail = detail[-2000:]


@dataclass(frozen=True)
class Limits:
    timeout_s: float = 300.0
    cpu_s: int = 600
    memory_bytes: int = 2 * 1024**3
    max_output_bytes: int = 1024**3
    threads: int = 2


DEFAULT_LIMITS = Limits()
# Only local files and pipes: an input can never make ffmpeg open a network connection.
PROTOCOLS = ["-protocol_whitelist", "file,pipe"]


def tool_path(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise MediaToolError(f"{name} is not installed or not on PATH")
    return found


def _rlimits(limits: Limits) -> Callable[[], None] | None:
    if sys.platform == "win32":
        return None

    def apply() -> None:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_s, limits.cpu_s))
        resource.setrlimit(resource.RLIMIT_AS, (limits.memory_bytes, limits.memory_bytes))
        resource.setrlimit(
            resource.RLIMIT_FSIZE, (limits.max_output_bytes, limits.max_output_bytes)
        )

    return apply


def _minimal_env() -> dict[str, str]:
    """Only what the tools need; Windows DLL loading also needs SYSTEMROOT."""
    keep = ("PATH", "SYSTEMROOT", "TEMP", "TMP")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["LC_ALL"] = "C"
    return env


def run_tool(
    name: str, args: Sequence[str | Path], limits: Limits = DEFAULT_LIMITS
) -> subprocess.CompletedProcess[str]:
    cmd = [tool_path(name), *(str(a) for a in args)]
    try:
        result = subprocess.run(  # noqa: S603  (fixed binary, argument list, no shell)
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=limits.timeout_s,
            stdin=subprocess.DEVNULL,
            preexec_fn=_rlimits(limits),
            env=_minimal_env(),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaToolError(f"{name} took longer than {limits.timeout_s:.0f}s") from exc
    if result.returncode != 0:
        raise MediaToolError(f"{name} failed (exit {result.returncode})", result.stderr)
    return result


def ffmpeg(args: Sequence[str | Path], limits: Limits = DEFAULT_LIMITS) -> str:
    """Run ffmpeg; returns stderr (ffmpeg logs there)."""
    base = ["-hide_banner", "-nostdin", "-loglevel", "error", "-threads", str(limits.threads)]
    return run_tool("ffmpeg", [*base, *PROTOCOLS, *args], limits).stderr


def ffprobe_json(path: Path, limits: Limits = DEFAULT_LIMITS) -> str:
    args = [
        "-v", "error", *PROTOCOLS, "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]  # fmt: skip
    return run_tool("ffprobe", args, limits).stdout
