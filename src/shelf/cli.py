"""Command line: run the whole pipeline on one video and write the catalog outputs.

  uv run python -m shelf.cli process VIDEO --shop "Sharma Sarees" --whatsapp "98765 43210"
  uv run python -m shelf.cli process VIDEO ... --fake evals/labels/synth_a.json   # offline

Uses the same settings as the API (.env); there is no review screen here, so every item with a
price is published and the questions the review screen would ask are printed instead.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from decimal import Decimal
from pathlib import Path

from engine.pipeline.publish import ShopInfo, publish
from engine.pipeline.run import Pipeline, StageEvent
from engine.providers.fake import Scenario, fake_providers
from engine.providers.meta import meta_providers
from engine.runlog import CallContext, JsonlRunLog, MemoryRunLog
from engine.spend import InMemorySpendLedger, SpendCapExceededError
from shelf.config import get_settings


class _TeeLog(MemoryRunLog):
    def __init__(self, jsonl: JsonlRunLog) -> None:
        super().__init__()
        self.jsonl = jsonl

    def record(self, entry):  # type: ignore[no-untyped-def]
        super().record(entry)
        self.jsonl.record(entry)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "shop"


def _print_event(event: StageEvent) -> None:
    mark = {"running": "...", "done": "done", "cached": "cached", "failed": "FAILED"}[event.status]
    print(f"  {event.stage:<12} {mark}" + (f"  {event.error}" if event.error else ""), flush=True)


async def process(args: argparse.Namespace) -> int:
    settings = get_settings()
    config = settings.engine_config()
    out = Path(args.out)
    log = _TeeLog(JsonlRunLog(out / "runlog.jsonl"))
    ledger = InMemorySpendLedger(config.caps)
    ctx = CallContext(job_id=out.name, workspace_id="cli", ledger=ledger, runlog=log)

    client = None
    if args.fake or config.providers == "fake":
        labels = Path(args.fake) if args.fake else None
        if labels is None:
            print("PROVIDERS=fake needs --fake LABELS.json", file=sys.stderr)
            return 2
        providers = fake_providers(Scenario.load(labels))
    else:
        providers, client = meta_providers(config)

    pipeline = Pipeline(providers, out / "work", ctx, ai_mark=not args.no_ai_mark,
                        on_event=_print_event)  # fmt: skip
    print(f"Processing {args.video}")
    try:
        result = await pipeline.run(Path(args.video))
    except SpendCapExceededError as exc:
        print(f"Stopped: {exc}. Try a shorter video or raise the cap.", file=sys.stderr)
        return 3
    finally:
        if client is not None:
            await client.aclose()

    slug = args.slug or _slug(args.shop)
    shop = ShopInfo(
        name=args.shop,
        slug=slug,
        whatsapp=args.whatsapp,
        public_base_url=args.base_url,
        media_base_url=f"{args.base_url.rstrip('/')}/media",
    )
    published = publish(shop, result.products, result.decisions, result.enriched,
                        result.images, out / "catalog")  # fmt: skip

    titles = {e.product_idx: e.title_en for e in result.enriched}
    print("\nItems")
    for d in result.decisions:
        price = f"Rs {d.price_inr}" if d.price_inr is not None else "no price"
        print(f"  {d.product_idx:>2}  {titles.get(d.product_idx, '?')[:40]:<40} {price:>10}"
              f"  {d.source} ({d.confidence:.2f})")  # fmt: skip
    if result.flags:
        print("\nQuestions for the seller")
        for f in result.flags:
            target = f"item {f.product_idx}" if f.product_idx else f"items {f.candidates}"
            print(f"  {f.kind:<18} {target}  {f.params or ''} {f.options or ''}")
    cost = sum((e.cost_usd for e in log.entries), Decimal(0))
    print(f"\nPublished {published.published} item(s); skipped {published.skipped or 'none'}")
    print(f"Feed:    {published.feed_csv}\nCatalog: {published.catalog_json}\n"
          f"Photos:  {published.images_zip}\nModel cost: ${cost:.4f} "
          f"({len(log.entries)} calls; run log {out / 'runlog.jsonl'})")  # fmt: skip
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shelf")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("process", help="video -> catalog, feed CSV and photos")
    p.add_argument("video")
    p.add_argument("--shop", required=True)
    p.add_argument("--whatsapp", required=True)
    p.add_argument("--slug")
    p.add_argument("--out", default="output/run")
    p.add_argument("--base-url", default="https://shelf-to-shop.example")
    p.add_argument("--fake", help="replay a labels JSON instead of calling models")
    p.add_argument("--no-ai-mark", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "process":
        return asyncio.run(process(args))
    return 1


if __name__ == "__main__":
    sys.exit(main())
