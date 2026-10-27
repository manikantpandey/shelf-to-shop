"""Cost estimates per provider call and spend caps per job and per day.

Prices: dev.meta.ai/docs/pricing-rate-limits.md, read 2026-10-27. Baseten lists the same token
prices for Muse Spark Open (baseten.co/library/muse-spark-open).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_UP, Decimal
from typing import Protocol

from engine.config import SpendCaps

MILLION = Decimal(1_000_000)
SPARK_INPUT_PER_M = Decimal("1.25")
SPARK_CACHED_INPUT_PER_M = Decimal("0.15")
SPARK_OUTPUT_PER_M = Decimal("4.25")
IMAGE_EACH = Decimal("0.01")
SAM_PER_IMAGE = Decimal("2.50") / 1000
SAM_PER_FRAME = Decimal("0.20") / 1000
SAM_MIN_FRAMES_PER_VIDEO = 50
TRANSCRIBE_PER_HOUR = Decimal("0.18")


def _usd(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"), rounding=ROUND_UP)


def spark_cost(input_tokens: int, output_tokens: int, cached_input_tokens: int = 0) -> Decimal:
    uncached = max(0, input_tokens - cached_input_tokens)
    return _usd(
        (
            uncached * SPARK_INPUT_PER_M
            + cached_input_tokens * SPARK_CACHED_INPUT_PER_M
            + output_tokens * SPARK_OUTPUT_PER_M
        )
        / MILLION
    )


def image_cost(images: int) -> Decimal:
    return _usd(images * IMAGE_EACH)


def sam_image_cost(images: int) -> Decimal:
    return _usd(images * SAM_PER_IMAGE)


def sam_video_cost(frames: int) -> Decimal:
    return _usd(max(frames, SAM_MIN_FRAMES_PER_VIDEO) * SAM_PER_FRAME)


def transcribe_cost(audio_seconds: float) -> Decimal:
    return _usd(Decimal(str(audio_seconds)) / 3600 * TRANSCRIBE_PER_HOUR)


class SpendCapExceededError(Exception):
    def __init__(self, scope: str, cap: Decimal, would_be: Decimal) -> None:
        super().__init__(f"{scope} spend cap ${cap} would be exceeded (${would_be})")
        self.scope = scope
        self.cap = cap
        self.would_be = would_be


@dataclass(frozen=True)
class Reservation:
    job_id: str
    workspace_id: str
    day: date
    amount: Decimal


class SpendLedger(Protocol):
    def reserve(self, job_id: str, workspace_id: str, amount: Decimal) -> Reservation: ...
    def settle(self, reservation: Reservation, actual: Decimal) -> None: ...


@dataclass
class InMemorySpendLedger:
    """Ledger for the CLI and tests. The API uses a DB-backed ledger with the same protocol."""

    caps: SpendCaps
    _job: dict[str, Decimal] = field(default_factory=dict)
    _workspace_day: dict[tuple[str, date], Decimal] = field(default_factory=dict)
    _instance_day: dict[date, Decimal] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def reserve(self, job_id: str, workspace_id: str, amount: Decimal) -> Reservation:
        today = datetime.now(UTC).date()
        with self._lock:
            checks = [
                ("job", self.caps.per_job_usd, self._job.get(job_id, Decimal(0))),
                (
                    "workspace daily",
                    self.caps.per_workspace_day_usd,
                    self._workspace_day.get((workspace_id, today), Decimal(0)),
                ),
                (
                    "instance daily",
                    self.caps.per_instance_day_usd,
                    self._instance_day.get(today, Decimal(0)),
                ),
            ]
            for scope, cap, spent in checks:
                if spent + amount > cap:
                    raise SpendCapExceededError(scope, cap, spent + amount)
            self._add(job_id, workspace_id, today, amount)
        return Reservation(job_id, workspace_id, today, amount)

    def settle(self, reservation: Reservation, actual: Decimal) -> None:
        with self._lock:
            self._add(
                reservation.job_id,
                reservation.workspace_id,
                reservation.day,
                actual - reservation.amount,
            )

    def spent_on_job(self, job_id: str) -> Decimal:
        return self._job.get(job_id, Decimal(0))

    def _add(self, job_id: str, workspace_id: str, day: date, delta: Decimal) -> None:
        self._job[job_id] = self._job.get(job_id, Decimal(0)) + delta
        key = (workspace_id, day)
        self._workspace_day[key] = self._workspace_day.get(key, Decimal(0)) + delta
        self._instance_day[day] = self._instance_day.get(day, Decimal(0)) + delta
