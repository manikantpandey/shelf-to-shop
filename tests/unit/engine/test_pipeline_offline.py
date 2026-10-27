"""The whole pipeline offline: fake providers, a generated clip, real ffmpeg and real exports."""

from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
import zipfile
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from engine.config import SpendCaps
from engine.export.provenance import COMPOSITE_SYNTHETIC
from engine.pipeline.publish import ShopInfo, publish
from engine.pipeline.run import Pipeline, StageEvent
from engine.providers.fake import FakeSegmenter, Scenario, fake_providers
from engine.runlog import CallContext, MemoryRunLog
from engine.spend import InMemorySpendLedger

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed"),
]

LABELS: dict[str, Any] = {
    "video": "test.mp4",
    "products": [
        {"n": 1, "what": "blue cotton saree", "appears_s": [0.0, 3.0], "spoken_price_inr": 1200,
         "spoken_at_s": 1.0, "spoken_end_s": 2.0, "spoken_words": "ye neela wala barah sau",
         "tag_price_inr": None},
        {"n": 2, "what": "red silk saree", "appears_s": [2.5, 6.0], "spoken_price_inr": 850,
         "spoken_at_s": 4.0, "spoken_end_s": 5.0, "spoken_words": "laal wala saadhe aath sau",
         "tag_price_inr": 900},
        {"n": 3, "what": "pink chiffon saree", "appears_s": [5.5, 8.0], "spoken_price_inr": None,
         "spoken_at_s": None, "spoken_end_s": None, "spoken_words": "aur ye gulabi wala",
         "tag_price_inr": None},
    ],
}  # fmt: skip


@pytest.fixture(scope="module")
def clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("clip") / "test.mp4"
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg is not None
    subprocess.run(  # noqa: S603
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=300:sample_rate=48000",
            "-t",
            "8",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )
    return path


def _pipeline(work: Path, events: list[StageEvent], providers: Any = None) -> Pipeline:
    ctx = CallContext("job", "ws", InMemorySpendLedger(SpendCaps()), MemoryRunLog())
    return Pipeline(
        providers or fake_providers(Scenario(LABELS)), work, ctx, on_event=events.append
    )


async def test_pipeline_end_to_end_offline(clip: Path, tmp_path: Path) -> None:
    events: list[StageEvent] = []
    result = await _pipeline(tmp_path / "work", events).run(clip)

    # detect and transcribe run concurrently, so compare as a set.
    done = {e.stage for e in events if e.status == "done"}
    assert done == {"ingest", "detect", "transcribe", "segment", "enrich", "match", "verify",
                    "backgrounds"}  # fmt: skip
    prices = {d.product_idx: d.price_inr for d in result.decisions}
    assert prices == {1: 1200, 2: 850, 3: None}
    kinds = {(f.kind, f.product_idx) for f in result.flags}
    assert ("price_conflict", 2) in kinds  # tag 900 vs spoken 850
    assert ("missing_price", 3) in kinds

    shop = ShopInfo(
        name="Sharma Sarees",
        slug="sharma",
        whatsapp="98765 43210",
        public_base_url="https://shop.example",
        media_base_url="https://cdn.example",
    )
    out = publish(shop, result.products, result.decisions, result.enriched, result.images,
                  tmp_path / "catalog")  # fmt: skip
    assert out.published == 2
    assert out.skipped == [("sharma-03", "no price")]

    rows = list(csv.DictReader(io.StringIO(out.feed_csv.read_text(encoding="utf-8"))))
    assert [(r["id"], r["price"]) for r in rows] == [("sharma-01", "1200.00 INR"),
                                                       ("sharma-02", "850.00 INR")]  # fmt: skip
    assert all(r["link"].startswith("https://shop.example/s/sharma/p/") for r in rows)

    catalog = json.loads(out.catalog_json.read_text(encoding="utf-8"))
    raw = json.dumps(catalog)
    for private in ("product_idx", "work", "mask", "frame", "@", "runlog"):
        assert private not in raw
    assert catalog["shop"]["whatsapp"] == "919876543210"
    assert catalog["products"][0]["order_link_en"].startswith("https://wa.me/919876543210?text=")
    assert catalog["products"][0]["price_display"] == "₹1,200"

    with zipfile.ZipFile(out.images_zip) as zf:
        assert sorted(zf.namelist()) == ["sharma-01.jpg", "sharma-02.jpg"]
        img = Image.open(io.BytesIO(zf.read("sharma-01.jpg")))
        assert img.size == (1024, 1024)
        assert COMPOSITE_SYNTHETIC.encode() in img.info["xmp"]


async def test_rerun_is_cached_and_resumes_after_a_failure(clip: Path, tmp_path: Path) -> None:
    work = tmp_path / "work"

    class Broken(FakeSegmenter):
        async def cutout(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("SAM is down")

    providers = fake_providers(Scenario(LABELS))
    healthy_segmenter = providers.segmenter
    providers.segmenter = Broken()
    events: list[StageEvent] = []
    with pytest.raises(RuntimeError, match="SAM is down"):
        await _pipeline(work, events, providers).run(clip)
    assert ("segment", "failed") in {(e.stage, e.status) for e in events}

    providers.segmenter = healthy_segmenter
    events = []
    await _pipeline(work, events, providers).run(clip)
    status = {e.stage: e.status for e in events if e.status in ("done", "cached")}
    assert status["ingest"] == status["detect"] == status["transcribe"] == "cached"
    assert status["segment"] == status["backgrounds"] == "done"

    events = []
    await _pipeline(work, events, providers).run(clip)
    assert {e.status for e in events} == {"cached"}


async def test_spend_cap_stops_the_job(clip: Path, tmp_path: Path) -> None:
    from engine.spend import SpendCapExceededError

    class Pricey(FakeSegmenter):
        async def cutout(self, ctx: CallContext, *args: Any, **kwargs: Any) -> Any:
            ctx.ledger.reserve(ctx.job_id, ctx.workspace_id, Decimal("1.00"))
            return await super().cutout(ctx, *args, **kwargs)

    providers = fake_providers(Scenario(LABELS))
    providers.segmenter = Pricey()
    with pytest.raises(SpendCapExceededError):
        await _pipeline(tmp_path / "work", [], providers).run(clip)
