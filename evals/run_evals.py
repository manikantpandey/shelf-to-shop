"""Run the labelled clips through the real pipeline and score it against the confirmed labels.

    uv run python evals/run_evals.py                  # every labelled clip whose video is present
    uv run python evals/run_evals.py real_kirana_a    # one clip
    uv run python evals/run_evals.py --fresh          # forget cached stages and pay again

Costs about $0.10 per 30 s clip (Meta Model API) the first time. Stages are cached per clip in
evals/out/<clip>/work, so after a change to matching or checking a rerun costs nothing; time and
cost in the report always come from the last full run. Detected items are paired with labelled ones
by shared screen time and description (evals/scoring.py). Writes evals/report.md (the table in the
README) and, git-ignored, evals/out/<clip>/.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scoring import Score, outcomes, score, total

from engine.pipeline.run import Pipeline
from engine.providers.meta import meta_providers
from engine.runlog import CallContext, JsonlRunLog, MemoryRunLog, RunLogEntry
from engine.spend import InMemorySpendLedger
from shelf.config import get_settings

ROOT = Path(__file__).resolve().parent
MANUAL_SECONDS_PER_ITEM = 90  # typing a name and price, taking and cropping a photo, by hand


class _Tee(MemoryRunLog):
    def __init__(self, jsonl: JsonlRunLog) -> None:
        super().__init__()
        self.jsonl = jsonl

    def record(self, entry: RunLogEntry) -> None:
        super().record(entry)
        self.jsonl.record(entry)


async def run_clip(label_file: Path, fresh: bool) -> Score:
    labels = json.loads(label_file.read_text(encoding="utf-8"))
    out = ROOT / "out" / label_file.stem
    work, full_run = out / "work", out / "full_run.json"
    if fresh or not full_run.exists():
        shutil.rmtree(work, ignore_errors=True)
        full_run.unlink(missing_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "runlog.jsonl").unlink(missing_ok=True)
    config = get_settings().engine_config()
    providers, client = meta_providers(config)
    log = _Tee(JsonlRunLog(out / "runlog.jsonl"))
    ctx = CallContext(job_id=label_file.stem, workspace_id="evals",
                      ledger=InMemorySpendLedger(config.caps), runlog=log)  # fmt: skip
    started = time.monotonic()
    try:
        result = await Pipeline(providers, work, ctx).run(ROOT / "videos" / labels["video"])
    finally:
        await client.aclose()
    if not full_run.exists():
        spent = {"seconds": time.monotonic() - started, "cost_usd": float(log.total_cost())}
        full_run.write_text(json.dumps(spent), encoding="utf-8")
    spent = json.loads(full_run.read_text(encoding="utf-8"))
    s = score(label_file.stem, labels, result, spent["seconds"], spent["cost_usd"])
    detail = {
        "score": asdict(s),
        "outcomes": outcomes(labels["products"], result),
        "products": [p.model_dump(mode="json") for p in result.products],
        "decisions": [d.model_dump(mode="json") for d in result.decisions],
        "flags": [f.model_dump(mode="json") for f in result.flags],
    }
    (out / "result.json").write_text(json.dumps(detail, ensure_ascii=False, indent=2), "utf-8")
    return s


def _row(s: Score, name: str) -> str:
    return (
        f"| {name} | {s.seconds_of_video:.0f} s | {s.labelled} | {s.found} | {s.recall:.0%} | "
        f"{s.precision:.0%} | {s.right}/{s.with_price} | {s.asked} | {s.wrong} | "
        f"{s.processing_s:.0f} s | ${s.cost_usd:.2f} |"
    )


def report(scores: list[Score]) -> str:
    all_ = total(scores)
    saved = all_.right * MANUAL_SECONDS_PER_ITEM / 60
    lines = [
        "| Clip | Video | Items labelled | Items found | Recall | Precision | Prices right "
        "| Asked the seller | Wrong, not asked | Processing | Cost |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
        *(_row(s, s.clip) for s in scores),
        _row(all_, "**All**"),
        "",
        "*Prices right* counts labelled items that were found and have a price. "
        "*Asked the seller* became a question in Review instead of a guess. "
        "*Wrong, not asked* is the outcome that must not happen: "
        "a wrong price published without a question.",
        "",
        f"Estimated manual time saved: {all_.right} items listed with the right price and a "
        f"photo, at about {MANUAL_SECONDS_PER_ITEM} s each by hand, is **{saved:.0f} minutes**, "
        f"for {all_.processing_s / 60:.1f} minutes of processing nobody has to watch.",
    ]
    if all_.seeded:
        lines += [
            "",
            "Seeded traps (price said before or after the item, two items of the same colour, "
            "a tag that disagrees with the spoken price, no price said): "
            f"**{all_.caught} of {all_.seeded}** ended with the right price or a question.",
        ]
    return "\n".join(lines) + "\n"


def main() -> int:
    fresh = "--fresh" in sys.argv
    wanted = {a for a in sys.argv[1:] if not a.startswith("--")}
    files = sorted(p for p in (ROOT / "labels").glob("*.json") if not p.name.startswith("_"))
    scores = []
    for f in files:
        if wanted and f.stem not in wanted:
            continue
        video = ROOT / "videos" / json.loads(f.read_text(encoding="utf-8"))["video"]
        if not video.exists():
            print(f"{f.stem}: video not in evals/videos, skipped")
            continue
        print(f"{f.stem}: running", flush=True)
        scores.append(asyncio.run(run_clip(f, fresh)))
        print(f"  {asdict(scores[-1])}", flush=True)
    if not scores:
        print("nothing to run")
        return 1
    text = report(scores)
    if not wanted:
        (ROOT / "report.md").write_text("# Evals\n\n" + text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
