from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from engine.config import SpendCaps
from engine.pipeline.schemas import Box, DetectedProduct
from engine.pipeline.segment import best_cutout, candidate_times, mask_quality
from engine.providers.errors import ProviderUnavailableError
from engine.providers.interfaces import MaskResult
from engine.runlog import CallContext, MemoryRunLog
from engine.spend import InMemorySpendLedger

pytestmark = pytest.mark.anyio


def _product(first: float = 10.0, last: float = 20.0, best: float = 15.0) -> DetectedProduct:
    return DetectedProduct(idx=1, description="jar", colour="blue", noun="jar",
                           first_seen_s=first, last_seen_s=last, best_frame_s=best,
                           box=Box(x1=10, y1=10, x2=90, y2=90))  # fmt: skip


def _mask(confidence: float | None, coverage: float = 0.2) -> MaskResult:
    m = np.zeros((100, 100), dtype=bool)
    m.flat[: int(coverage * 10_000)] = True
    return MaskResult(m, confidence, "point")


def test_candidate_times_stay_inside_the_window() -> None:
    assert candidate_times(_product()) == [15.0, 14.0, 16.0]
    assert candidate_times(_product(10, 11, 10.0)) == [10.0, 10.25]
    assert candidate_times(_product(5, 5, 5)) == [5]


def test_mask_quality_prefers_confident_plausible_masks() -> None:
    assert mask_quality(None) == 0
    assert mask_quality(_mask(0.95)) > mask_quality(_mask(0.6))
    assert mask_quality(_mask(0.95, coverage=0.9)) < mask_quality(_mask(0.95))


class _Scripted:
    def __init__(self, results: list[MaskResult | Exception | None]) -> None:
        self.results = results
        self.calls = 0

    async def cutout(self, *args: Any) -> MaskResult | None:
        self.calls += 1
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _ctx() -> CallContext:
    return CallContext("j", "w", InMemorySpendLedger(SpendCaps()), MemoryRunLog())


async def _frames(t: float, attempt: int) -> Path:
    return Path(f"frame_{attempt}.jpg")


async def test_weak_first_frame_tries_neighbours_and_keeps_the_best() -> None:
    seg = _Scripted([_mask(0.5), _mask(0.92), _mask(0.99)])
    found = await best_cutout(_ctx(), seg, _product(), _frames)  # type: ignore[arg-type]
    assert found is not None
    result, frame = found
    assert result.confidence == 0.92 and frame == Path("frame_1.jpg")
    assert seg.calls == 2  # stopped once good enough


async def test_good_first_frame_costs_one_call() -> None:
    seg = _Scripted([_mask(0.95)])
    found = await best_cutout(_ctx(), seg, _product(), _frames)  # type: ignore[arg-type]
    assert found is not None and seg.calls == 1


async def test_provider_errors_on_one_frame_do_not_lose_the_item() -> None:
    down = ProviderUnavailableError("busy", provider="meta")
    seg = _Scripted([down, None, _mask(0.7)])
    found = await best_cutout(_ctx(), seg, _product(), _frames)  # type: ignore[arg-type]
    assert found is not None and found[1] == Path("frame_2.jpg")
