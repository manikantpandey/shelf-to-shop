from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.orm import Session, sessionmaker

from shelf.db.base import Base
from shelf.db.models.task import Task
from shelf.db.session import make_engine, make_session_factory
from shelf.jobs import queue
from shelf.jobs.worker import PermanentTaskError, Worker

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'q.db'}")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _enqueue(factory: sessionmaker[Session], **kw: object) -> Task:
    with factory.begin() as s:
        task = queue.enqueue(s, "pipeline", {"job_id": "j1"}, **kw)  # type: ignore[arg-type]
        s.expunge(task)
    return task


def _get(factory: sessionmaker[Session], task_id: object) -> Task:
    with factory() as s:
        task = s.get(Task, task_id)
        assert task is not None
        s.expunge(task)
        return task


def test_migrations_upgrade_and_downgrade(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    assert "tasks" in inspect(make_engine(url)).get_table_names()
    command.downgrade(cfg, "base")
    assert "tasks" not in inspect(make_engine(url)).get_table_names()


def test_claim_takes_a_lease(factory: sessionmaker[Session]) -> None:
    task = _enqueue(factory)
    claimed = queue.claim(factory, "w1", ["pipeline"])
    assert claimed is not None and claimed.id == task.id
    assert claimed.status == "running"
    assert claimed.attempts == 1
    assert claimed.lease_owner == "w1"
    assert queue.claim(factory, "w2", ["pipeline"]) is None


def test_other_kinds_and_future_tasks_are_not_claimed(factory: sessionmaker[Session]) -> None:
    _enqueue(factory, run_at=datetime.now(UTC) + timedelta(hours=1))
    assert queue.claim(factory, "w1", ["pipeline"]) is None
    assert queue.claim(factory, "w1", ["webhook"]) is None


def test_expired_lease_can_be_taken_over(factory: sessionmaker[Session]) -> None:
    _enqueue(factory)
    first = queue.claim(factory, "w1", ["pipeline"], lease_s=60)
    assert first is not None
    later = datetime.now(UTC) + timedelta(seconds=120)
    second = queue.claim(factory, "w2", ["pipeline"], clock=lambda: later)
    assert second is not None
    assert second.lease_owner == "w2"
    assert second.attempts == 2
    with factory.begin() as s:
        assert not queue.complete(s, first.id, "w1")  # the crashed worker lost it
        assert queue.complete(s, second.id, "w2")


def test_only_one_of_many_concurrent_claimers_wins(factory: sessionmaker[Session]) -> None:
    _enqueue(factory)
    wins: list[str] = []
    barrier = threading.Barrier(6)

    def worker(name: str) -> None:
        barrier.wait()
        if queue.claim(factory, name, ["pipeline"]) is not None:
            wins.append(name)

    threads = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(wins) == 1


def test_failure_requeues_with_backoff_then_dies(factory: sessionmaker[Session]) -> None:
    task = _enqueue(factory, max_attempts=2)
    queue.claim(factory, "w1", ["pipeline"])
    with factory.begin() as s:
        assert queue.fail(s, task.id, "w1", "boom") == "queued"
    requeued = _get(factory, task.id)
    assert queue._aware(requeued.run_at) >= datetime.now(UTC) - timedelta(seconds=1)
    assert requeued.last_error == "boom"
    future = datetime.now(UTC) + timedelta(hours=1)
    assert queue.claim(factory, "w1", ["pipeline"], clock=lambda: future) is not None
    with factory.begin() as s:
        assert queue.fail(s, task.id, "w1", "boom again") == "dead"


def test_non_retryable_failure_is_dead_at_once(factory: sessionmaker[Session]) -> None:
    task = _enqueue(factory)
    queue.claim(factory, "w1", ["pipeline"])
    with factory.begin() as s:
        assert queue.fail(s, task.id, "w1", "bad input", retryable=False) == "dead"


def test_heartbeat_only_for_owner(factory: sessionmaker[Session]) -> None:
    task = _enqueue(factory)
    queue.claim(factory, "w1", ["pipeline"])
    with factory.begin() as s:
        assert queue.heartbeat(s, task.id, "w1")
        assert not queue.heartbeat(s, task.id, "w2")


def test_worker_runs_handlers_and_records_outcomes(factory: sessionmaker[Session]) -> None:
    ok = _enqueue(factory, priority=1)
    flaky = _enqueue(factory, priority=2)
    bad = _enqueue(factory, priority=3)
    seen: list[object] = []

    def handler(task: Task) -> None:
        seen.append(task.id)
        if task.id == flaky.id:
            raise RuntimeError("provider down")
        if task.id == bad.id:
            raise PermanentTaskError("video rejected")

    worker = Worker(factory, {"pipeline": handler}, worker_id="w1")
    assert worker.run_once() and worker.run_once() and worker.run_once()
    assert not worker.run_once()
    assert seen == [ok.id, flaky.id, bad.id]
    assert _get(factory, ok.id).status == "done"
    assert _get(factory, flaky.id).status == "queued"
    assert _get(factory, bad.id).status == "dead"
