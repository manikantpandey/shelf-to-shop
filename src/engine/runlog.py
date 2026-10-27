"""Auditable run log: one entry per provider call, plus the call context that carries it."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol

from engine.spend import SpendLedger


@dataclass(frozen=True)
class RunLogEntry:
    job_id: str
    stage: str
    provider: str
    model: str
    operation: str
    latency_ms: int
    attempts: int
    cost_usd: Decimal
    input_tokens: int = 0
    output_tokens: int = 0
    inputs_summary: dict[str, Any] = field(default_factory=dict)
    outputs_summary: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def as_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["cost_usd"] = str(self.cost_usd)
        return data


class RunLog(Protocol):
    def record(self, entry: RunLogEntry) -> None: ...


@dataclass
class MemoryRunLog:
    entries: list[RunLogEntry] = field(default_factory=list)

    def record(self, entry: RunLogEntry) -> None:
        self.entries.append(entry)

    def total_cost(self) -> Decimal:
        return sum((e.cost_usd for e in self.entries), Decimal(0))


@dataclass
class JsonlRunLog:
    """Append-only JSON-lines log, used by the CLI."""

    path: Path
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, entry: RunLogEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry.as_json(), ensure_ascii=False)
        with self._lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


@dataclass(frozen=True)
class CallContext:
    """Who a provider call is for: spend is charged and logged against this job and stage."""

    job_id: str
    workspace_id: str
    ledger: SpendLedger
    runlog: RunLog
    stage: str = ""

    def for_stage(self, stage: str) -> CallContext:
        return replace(self, stage=stage)
