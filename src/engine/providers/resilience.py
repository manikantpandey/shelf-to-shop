"""Timeouts, jittered retries and a circuit breaker around provider calls."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

import httpx

from engine.providers.errors import (
    CircuitOpenError,
    ProviderError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 3
    base_delay_s: float = 0.75
    max_delay_s: float = 20.0
    # If the provider asks us to wait longer than this, fail now and let the job be retried later.
    max_retry_after_s: float = 90.0

    def delay_s(self, attempt: int, retry_after_s: float | None, rng: random.Random) -> float:
        """Full-jitter exponential backoff, never shorter than the provider's Retry-After."""
        backoff = rng.uniform(0, min(self.max_delay_s, self.base_delay_s * (2**attempt)))
        return max(backoff, retry_after_s or 0.0)


@dataclass
class CircuitBreaker:
    """Opens after N consecutive health failures; allows one trial call after the cooldown."""

    name: str
    failure_threshold: int = 5
    reset_timeout_s: float = 30.0
    clock: Callable[[], float] = time.monotonic
    _failures: int = field(default=0, init=False)
    _opened_at: float | None = field(default=None, init=False)
    _trial_in_flight: bool = field(default=False, init=False)

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if self.clock() - self._opened_at >= self.reset_timeout_s:
            return "half_open"
        return "open"

    def before_call(self) -> None:
        state = self.state
        if state == "open" or (state == "half_open" and self._trial_in_flight):
            raise CircuitOpenError(
                "provider paused after repeated failures; try again shortly", provider=self.name
            )
        if state == "half_open":
            self._trial_in_flight = True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._trial_in_flight = False

    def record_failure(self) -> None:
        self._trial_in_flight = False
        self._failures += 1
        if self._opened_at is not None or self._failures >= self.failure_threshold:
            self._opened_at = self.clock()


@dataclass
class CallStats:
    attempts: int = 0
    latency_ms: int = 0
    last_error: str | None = None


class Resilient:
    """Runs an async provider call with a deadline, retries and a shared circuit breaker."""

    def __init__(
        self,
        name: str,
        *,
        policy: RetryPolicy | None = None,
        breaker: CircuitBreaker | None = None,
        timeout_s: float = 120.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self.name = name
        self.policy = policy or RetryPolicy()
        self.breaker = breaker or CircuitBreaker(name)
        self.timeout_s = timeout_s
        self._sleep = sleep
        self._rng = rng or random.Random()  # noqa: S311  (jitter, not security)

    async def call(self, fn: Callable[[], Awaitable[T]], stats: CallStats | None = None) -> T:
        stats = stats if stats is not None else CallStats()
        started = time.perf_counter()
        try:
            return await self._call(fn, stats)
        finally:
            stats.latency_ms = round((time.perf_counter() - started) * 1000)

    async def _call(self, fn: Callable[[], Awaitable[T]], stats: CallStats) -> T:
        attempt = 0
        while True:
            self.breaker.before_call()
            stats.attempts += 1
            try:
                result = await asyncio.wait_for(fn(), timeout=self.timeout_s)
            except TimeoutError:
                error: ProviderError = ProviderTimeoutError(
                    f"no answer within {self.timeout_s:.0f}s", provider=self.name
                )
            except httpx.TransportError as exc:
                error = ProviderUnavailableError(
                    f"network error: {type(exc).__name__}", provider=self.name
                )
            except ProviderError as exc:
                error = exc
            else:
                self.breaker.record_success()
                return result

            stats.last_error = str(error)
            if error.counts_against_health:
                self.breaker.record_failure()
            retry_after = error.retry_after_s
            too_long = retry_after is not None and retry_after > self.policy.max_retry_after_s
            if not error.retryable or attempt >= self.policy.max_retries or too_long:
                raise error
            await self._sleep(self.policy.delay_s(attempt, retry_after, self._rng))
            attempt += 1
