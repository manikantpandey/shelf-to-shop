"""DB-backed durable queue with leases.

Enqueue in the same transaction as the job row, so a job never exists without its task. A claim
is a conditional UPDATE (status/lease checked in the WHERE clause), so only one worker wins a task,
even on SQLite; on Postgres, SKIP LOCKED keeps concurrent workers off each other's candidates.
An expired lease (crashed worker) makes the task claimable again.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from shelf.db.models.task import Task

Clock = Callable[[], datetime]


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    # SQLite returns naive datetimes; everything we store is UTC.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _rowcount(result: object) -> int:
    return cast(CursorResult[Any], result).rowcount


def enqueue(
    session: Session,
    kind: str,
    payload: dict[str, Any],
    *,
    run_at: datetime | None = None,
    priority: int = 100,
    max_attempts: int = 5,
) -> Task:
    task = Task(
        kind=kind,
        payload=payload,
        run_at=run_at or _now(),
        priority=priority,
        max_attempts=max_attempts,
    )
    session.add(task)
    session.flush()
    return task


def claim(
    factory: sessionmaker[Session],
    worker_id: str,
    kinds: Sequence[str],
    *,
    lease_s: float = 300,
    clock: Clock = _now,
) -> Task | None:
    now = clock()
    claimable = or_(
        Task.status == "queued",
        (Task.status == "running") & (Task.lease_expires_at < now),
    )
    with factory() as session, session.begin():
        candidates = session.scalars(
            select(Task.id)
            .where(Task.kind.in_(kinds), Task.run_at <= now, claimable)
            .order_by(Task.priority, Task.run_at)
            .limit(5)
            .with_for_update(skip_locked=True)
        ).all()
        for task_id in candidates:
            won = _rowcount(
                session.execute(
                    update(Task)
                    .where(Task.id == task_id, claimable)
                    .values(
                        status="running",
                        lease_owner=worker_id,
                        lease_expires_at=now + timedelta(seconds=lease_s),
                        attempts=Task.attempts + 1,
                        updated_at=now,
                    )
                    .execution_options(synchronize_session=False)
                )
            )
            if won:
                task = session.get(Task, task_id, populate_existing=True)
                if task is not None:
                    session.expunge(task)
                return task
    return None


def heartbeat(
    session: Session, task_id: Any, worker_id: str, *, lease_s: float = 300, clock: Clock = _now
) -> bool:
    """Extend the lease. False means another worker took the task over."""
    result = session.execute(
        update(Task)
        .where(Task.id == task_id, Task.lease_owner == worker_id, Task.status == "running")
        .values(lease_expires_at=clock() + timedelta(seconds=lease_s))
    )
    return bool(_rowcount(result))


def complete(session: Session, task_id: Any, worker_id: str) -> bool:
    result = session.execute(
        update(Task)
        .where(Task.id == task_id, Task.lease_owner == worker_id, Task.status == "running")
        .values(status="done", lease_owner=None, lease_expires_at=None, last_error=None)
    )
    return bool(_rowcount(result))


def retry_delay_s(attempt: int, base_s: float = 10.0, cap_s: float = 600.0) -> float:
    return random.uniform(0, min(cap_s, base_s * 2**attempt))  # noqa: S311  (jitter)


def fail(
    session: Session,
    task_id: Any,
    worker_id: str,
    error: str,
    *,
    retryable: bool = True,
    clock: Clock = _now,
) -> str:
    """Record a failure: re-queue with backoff, or mark dead. Returns the new status."""
    task = session.get(Task, task_id)
    if task is None or task.lease_owner != worker_id:
        return "lost"
    dead = not retryable or task.attempts >= task.max_attempts
    task.status = "dead" if dead else "queued"
    task.last_error = error[:2000]
    task.lease_owner = None
    task.lease_expires_at = None
    if not dead:
        task.run_at = clock() + timedelta(seconds=retry_delay_s(task.attempts))
    return task.status


def lease_expired(task: Task, now: datetime | None = None) -> bool:
    expires = task.lease_expires_at
    return expires is not None and _aware(expires) < (now or _now())
