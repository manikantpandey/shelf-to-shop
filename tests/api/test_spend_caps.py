"""Daily spend caps hold across jobs and workers; a refused reservation leaves no trace."""

from __future__ import annotations

import threading
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from engine.config import SpendCaps
from engine.spend import SpendCapExceededError
from shelf.db.base import Base
from shelf.db.session import make_engine, make_session_factory
from shelf.jobs.service import _describe
from shelf.jobs.spend import DbSpendLedger

CAPS = SpendCaps(
    per_job_usd=Decimal("0.50"),
    per_workspace_day_usd=Decimal("1.00"),
    per_instance_day_usd=Decimal("1.50"),
)
DAY = date(2026, 10, 29)


@pytest.fixture
def factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'spend.db'}")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _ledger(factory: sessionmaker[Session], day: date = DAY) -> DbSpendLedger:
    return DbSpendLedger(factory, CAPS, today=lambda: day)


def test_a_shops_daily_cap_counts_every_job(factory: sessionmaker[Session]) -> None:
    first, second = _ledger(factory), _ledger(factory)  # two runs, as two workers would make
    first.reserve("job-1", "shop-a", Decimal("0.40"))
    first.reserve("job-1", "shop-a", Decimal("0.05"))
    second.reserve("job-2", "shop-a", Decimal("0.40"))
    with pytest.raises(SpendCapExceededError) as caught:
        _ledger(factory).reserve("job-3", "shop-a", Decimal("0.20"))  # 1.05 today
    assert caught.value.scope == "workspace daily"
    assert _ledger(factory).spent_today("shop-a") == Decimal("0.85")


def test_the_job_cap_still_applies_per_run(factory: sessionmaker[Session]) -> None:
    ledger = _ledger(factory)
    ledger.reserve("job-1", "shop-a", Decimal("0.45"))
    with pytest.raises(SpendCapExceededError) as caught:
        ledger.reserve("job-1", "shop-a", Decimal("0.10"))
    assert caught.value.scope == "job"


def test_settling_replaces_the_estimate_with_the_actual_cost(
    factory: sessionmaker[Session],
) -> None:
    ledger = _ledger(factory)
    held = ledger.reserve("job-1", "shop-a", Decimal("0.30"))
    ledger.settle(held, Decimal("0.12"))
    assert ledger.spent_today("shop-a") == Decimal("0.12")
    # The money freed by settling can be spent again today.
    _ledger(factory).reserve("job-2", "shop-a", Decimal("0.45"))
    _ledger(factory).reserve("job-3", "shop-a", Decimal("0.43"))


def test_the_service_cap_covers_all_shops_and_refusals_leave_no_trace(
    factory: sessionmaker[Session],
) -> None:
    _ledger(factory).reserve("j1", "shop-a", Decimal("0.50"))
    _ledger(factory).reserve("j2", "shop-b", Decimal("0.50"))
    _ledger(factory).reserve("j3", "shop-c", Decimal("0.40"))
    with pytest.raises(SpendCapExceededError) as caught:
        _ledger(factory).reserve("j4", "shop-d", Decimal("0.20"))
    assert caught.value.scope == "instance daily"
    # shop-d's own total was rolled back with the refused reservation.
    assert _ledger(factory).spent_today("shop-d") == Decimal(0)


def test_a_new_day_starts_from_nothing(factory: sessionmaker[Session]) -> None:
    for job in ("j1", "j2"):
        _ledger(factory).reserve(job, "shop-a", Decimal("0.50"))
    with pytest.raises(SpendCapExceededError):
        _ledger(factory).reserve("j3", "shop-a", Decimal("0.01"))
    tomorrow = _ledger(factory, date(2026, 10, 30))
    tomorrow.reserve("j3", "shop-a", Decimal("0.50"))


def test_parallel_reservations_never_overshoot(factory: sessionmaker[Session]) -> None:
    granted: list[Decimal] = []
    lock = threading.Lock()

    def worker(n: int) -> None:
        ledger = _ledger(factory)  # one ledger per worker: only the database is shared
        for i in range(10):
            try:
                ledger.reserve(f"job-{n}-{i}", "shop-a", Decimal("0.03"))
            except SpendCapExceededError:
                continue
            with lock:
                granted.append(Decimal("0.03"))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(granted) <= CAPS.per_workspace_day_usd
    assert _ledger(factory).spent_today("shop-a") == sum(granted)


def test_each_cap_has_its_own_message() -> None:
    codes = {
        _describe(SpendCapExceededError(scope, Decimal(1), Decimal(2)))[0]
        for scope in ("job", "workspace daily", "instance daily")
    }
    assert codes == {"spend_cap", "daily_cap", "service_daily_cap"}
