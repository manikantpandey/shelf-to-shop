"""Queue worker: claim a task, run its handler, record the outcome.

Run: uv run python -m shelf.jobs.worker
"""

from __future__ import annotations

import os
import random
import signal
import socket
import threading
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from shelf.config import get_settings
from shelf.core.logging import configure_logging, get_logger
from shelf.db.models.task import Task
from shelf.db.session import make_engine, make_session_factory
from shelf.jobs import queue

Handler = Callable[[Task], None]
log = get_logger(__name__)


class PermanentTaskError(Exception):
    """Raise from a handler when retrying cannot help (bad input, cap reached)."""


class Worker:
    def __init__(
        self,
        factory: sessionmaker[Session],
        handlers: dict[str, Handler],
        *,
        worker_id: str | None = None,
        lease_s: float = 300,
        idle_sleep_s: float = 1.0,
    ) -> None:
        self.factory = factory
        self.handlers = handlers
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self.lease_s = lease_s
        self.idle_sleep_s = idle_sleep_s
        self._stop = threading.Event()

    def stop(self, *_: Any) -> None:
        self._stop.set()

    def run_once(self) -> bool:
        """Process at most one task. Returns True if a task was claimed."""
        task = queue.claim(self.factory, self.worker_id, list(self.handlers), lease_s=self.lease_s)
        if task is None:
            return False
        bound = log.bind(task_id=str(task.id), kind=task.kind, attempt=task.attempts)
        bound.info("task_started")
        try:
            self.handlers[task.kind](task)
        except PermanentTaskError as exc:
            with self.factory.begin() as session:
                queue.fail(session, task.id, self.worker_id, str(exc), retryable=False)
            bound.warning("task_dead", error=str(exc))
        except Exception as exc:
            with self.factory.begin() as session:
                status = queue.fail(
                    session, task.id, self.worker_id, f"{type(exc).__name__}: {exc}"
                )
            bound.error("task_failed", status=status, error_type=type(exc).__name__)
        else:
            with self.factory.begin() as session:
                queue.complete(session, task.id, self.worker_id)
            bound.info("task_done")
        return True

    def run_forever(self) -> None:
        while not self._stop.is_set():
            if not self.run_once():
                self._stop.wait(self.idle_sleep_s * (0.5 + random.random()))  # noqa: S311


def main() -> None:
    from pathlib import Path

    from shelf.jobs.service import PIPELINE_TASK, run_pipeline_job
    from shelf.storage import LocalStorage

    settings = get_settings()
    configure_logging(settings.log_level)
    factory = make_session_factory(make_engine(settings.database_url))
    storage = LocalStorage(Path(settings.storage_dir))
    worker = Worker(
        factory,
        handlers={
            PIPELINE_TASK: lambda task: run_pipeline_job(
                factory, settings, storage, task.payload["job_id"]
            )
        },
        lease_s=900,  # a pipeline run takes a few minutes
    )
    signal.signal(signal.SIGINT, worker.stop)
    signal.signal(signal.SIGTERM, worker.stop)
    log.info("worker_started", worker_id=worker.worker_id)
    worker.run_forever()


if __name__ == "__main__":
    main()
