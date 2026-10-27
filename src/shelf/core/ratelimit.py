"""Rate limits for the endpoints anyone can call (orders, counters, sign-in) and for uploads.

A sliding window kept in memory: enough for one server (the deployment runs one API process).
Keys are hashed so no IP address or account id is kept in clear; they expire with their window.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import deque
from dataclasses import dataclass

from fastapi import Request

from shelf.core.errors import AppError


@dataclass(frozen=True)
class Limit:
    name: str
    count: int
    window_s: float


# Tuned for a small shop: a real customer never comes close; a script hits them at once.
ORDER_PER_IP = Limit("order-ip", 10, 600)
ORDER_PER_SHOP = Limit("order-shop", 120, 3600)
EVENT_PER_IP = Limit("event-ip", 120, 60)
SIGNIN_PER_IP = Limit("signin-ip", 20, 600)
UPLOAD_PER_SELLER = Limit("upload-seller", 30, 3600)
PHOTO_PER_SELLER = Limit("photo-seller", 120, 3600)


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, limit: Limit, key: str) -> None:
        """Count one call; raise 429 with a plain message once the limit is reached."""
        now = time.monotonic()
        name = f"{limit.name}:{hashlib.sha256(key.encode()).hexdigest()[:24]}"
        with self._lock:
            calls = self._hits.setdefault(name, deque())
            while calls and now - calls[0] > limit.window_s:
                calls.popleft()
            if len(calls) >= limit.count:
                wait = max(1, int(limit.window_s - (now - calls[0])))
                raise AppError(
                    "too_many",
                    "Too many tries in a short time. Wait a few minutes and try again.",
                    status=429,
                    extra={"retry_after_s": wait},
                )
            calls.append(now)
            if len(self._hits) > 50_000:
                self._forget(now)

    def _forget(self, now: float) -> None:
        for name in [n for n, c in self._hits.items() if not c or now - c[-1] > 3600]:
            del self._hits[name]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def limiter(request: Request) -> RateLimiter:
    found: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    if found is None:
        found = RateLimiter()
        request.app.state.rate_limiter = found
    return found
