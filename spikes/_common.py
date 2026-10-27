"""Shared helpers for spike scripts.

Keys come from the environment or the gitignored .env file. Nothing here prints a key or an
Authorization header.
"""

from __future__ import annotations

import base64
import json
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "spikes" / "out"

# Published prices (dev.meta.ai/docs/pricing-rate-limits.md, read 2026-10-27), in USD.
PRICE_SPARK_INPUT_PER_M = 1.25
PRICE_SPARK_OUTPUT_PER_M = 4.25
PRICE_IMAGE_EACH = 0.01
PRICE_SAM_PER_IMAGE = 2.50 / 1000
PRICE_SAM_PER_FRAME = 0.20 / 1000
PRICE_TRANSCRIBE_PER_HOUR = 0.18


def load_env() -> None:
    """Load KEY=VALUE pairs from .env without overriding real environment variables."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"{name} is not set. Add it to .env (see .env.example).")
    return value


def model_id(name: str, default: str) -> str:
    value = os.environ.get(name, default)
    if "contributor" in value.lower():
        raise SystemExit(f"{name}={value}: contributor models let Meta train on uploads; refusing.")
    return value


def meta_base_url() -> str:
    return os.environ.get("META_API_BASE_URL", "https://api.meta.ai/v1")


def meta_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {require('META_API_KEY')}"}


def describe_error(response: httpx.Response) -> str:
    """Summarise an API error without echoing request headers."""
    try:
        err = response.json().get("error", {})
        return (
            f"HTTP {response.status_code} code={err.get('code')} type={err.get('type')} "
            f"param={err.get('param')} message={err.get('message')}"
        )
    except (ValueError, AttributeError):
        return f"HTTP {response.status_code} body={response.text[:300]!r}"


def data_url(path: Path) -> str:
    mime = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }[path.suffix.lower()]
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


async def sse_events(response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    """Yield JSON payloads from a Server-Sent Events response."""
    async for line in response.aiter_lines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload and payload != "[DONE]":
            yield json.loads(payload)


class Timer:
    def __enter__(self) -> Timer:
        self.start = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self.ms = round((time.perf_counter() - self.start) * 1000)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
