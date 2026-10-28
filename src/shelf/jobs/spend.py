"""Spend caps that hold across jobs and workers.

The per-job cap is counted in memory (one ledger per run). Daily totals per shop and for the whole
service live in `spend_days`, and each reservation is one guarded UPDATE per scope inside a single
transaction: two workers cannot both slip under a cap, and a refused reservation leaves no trace.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import date
from decimal import ROUND_UP, Decimal
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from engine.config import SpendCaps
from engine.spend import Reservation, SpendCapExceededError
from shelf.core.clock import india_today
from shelf.db.models import SpendDay

MICROS = Decimal(1_000_000)
SERVICE = "service"


def _micros(usd: Decimal) -> int:
    return int((usd * MICROS).to_integral_value(rounding=ROUND_UP))


def shop_scope(workspace_id: str) -> str:
    return f"shop:{workspace_id}"


class DbSpendLedger:
    def __init__(
        self,
        factory: sessionmaker[Session],
        caps: SpendCaps,
        today: Callable[[], date] = india_today,
    ) -> None:
        self.factory, self.caps, self.today = factory, caps, today
        self._job: dict[str, Decimal] = {}
        self._lock = threading.Lock()

    def reserve(self, job_id: str, workspace_id: str, amount: Decimal) -> Reservation:
        day = self.today()
        with self._lock:
            spent = self._job.get(job_id, Decimal(0))
            if spent + amount > self.caps.per_job_usd:
                raise SpendCapExceededError("job", self.caps.per_job_usd, spent + amount)
            scopes = [
                (shop_scope(workspace_id), "workspace daily", self.caps.per_workspace_day_usd),
                (SERVICE, "instance daily", self.caps.per_instance_day_usd),
            ]
            with self.factory.begin() as db:
                for scope, label, cap in scopes:
                    self._ensure(db, scope, day)
                    if not self._add(db, scope, day, _micros(amount), limit=_micros(cap)):
                        current = db.scalar(
                            select(SpendDay.micros).where(
                                SpendDay.scope == scope, SpendDay.day == day
                            )
                        )
                        # Leaving the block rolls back any scope already added.
                        raise SpendCapExceededError(
                            label, cap, Decimal(current or 0) / MICROS + amount
                        )
            self._job[job_id] = spent + amount
        return Reservation(job_id, workspace_id, day, amount)

    def settle(self, reservation: Reservation, actual: Decimal) -> None:
        delta = _micros(actual) - _micros(reservation.amount)
        with self._lock:
            self._job[reservation.job_id] = (
                self._job.get(reservation.job_id, Decimal(0)) + actual - reservation.amount
            )
            if delta == 0:
                return
            with self.factory.begin() as db:
                for scope in (shop_scope(reservation.workspace_id), SERVICE):
                    self._add(db, scope, reservation.day, delta)

    def spent_today(self, workspace_id: str) -> Decimal:
        with self.factory() as db:
            micros = db.scalar(
                select(SpendDay.micros).where(
                    SpendDay.scope == shop_scope(workspace_id), SpendDay.day == self.today()
                )
            )
        return Decimal(micros or 0) / MICROS

    @staticmethod
    def _ensure(db: Session, scope: str, day: date) -> None:
        found = db.scalar(select(SpendDay.id).where(SpendDay.scope == scope, SpendDay.day == day))
        if found is None:
            try:
                with db.begin_nested():
                    db.add(SpendDay(scope=scope, day=day, micros=0))
            except IntegrityError:
                pass  # another worker made the row first

    @staticmethod
    def _add(db: Session, scope: str, day: date, micros: int, limit: int | None = None) -> bool:
        stmt = (
            update(SpendDay)
            .where(SpendDay.scope == scope, SpendDay.day == day)
            .values(micros=SpendDay.micros + micros)
            .execution_options(synchronize_session=False)
        )
        if limit is not None:
            stmt = stmt.where(SpendDay.micros + micros <= limit)
        return cast(CursorResult[Any], db.execute(stmt)).rowcount == 1
