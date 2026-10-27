"""Build the sample shop that demo sign-ins copy, from real shelf videos and the real models.

    uv run python scripts/seed_demo.py --name "Sharma General Store" --whatsapp "98765 43210" \\
        --publish 2 evals/videos/a.mp4 evals/videos/b.mp4 evals/videos/c.mp4

Runs each video through the full pipeline (PROVIDERS from .env; about $0.10 per 30 s clip),
publishes the first --publish videos after settling their questions (keep the price the seller
said; drop items with no price), and leaves the rest waiting for review so the demo can show the
review screen. --reset deletes an earlier sample shop first. Only use videos you own.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from engine.export.whatsapp import normalise_number
from engine.media.probe import MediaRejectedError, MediaRules, probe, sniff_container
from shelf.catalog.publish import publish_job
from shelf.config import get_settings
from shelf.db.models import FlagRow, Job, Product, Upload, User, Workspace
from shelf.db.session import make_engine, make_session_factory
from shelf.jobs.service import create_job, run_pipeline_job
from shelf.jobs.worker import PermanentTaskError
from shelf.storage import LocalStorage

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("videos", nargs="+", type=Path)
    ap.add_argument("--name", required=True, help="shop name shown to demo visitors")
    ap.add_argument("--whatsapp", required=True, help="number that 'Order on WhatsApp' opens")
    ap.add_argument("--publish", type=int, default=None, help="how many videos to publish")
    ap.add_argument("--reset", action="store_true", help="delete the previous sample shop")
    args = ap.parse_args()

    settings = get_settings()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "head")
    factory = make_session_factory(make_engine(settings.database_url))
    storage = LocalStorage(Path(settings.storage_dir))
    publish_count = len(args.videos) - 1 if args.publish is None else args.publish

    with factory.begin() as db:
        old = db.scalars(select(Workspace).where(Workspace.is_template.is_(True))).all()
        if old and not args.reset:
            print("A sample shop already exists; pass --reset to replace it.", file=sys.stderr)
            return 2
        for stale in old:
            storage.delete(f"ws/{stale.id}")
            stale_owner = db.get(User, stale.owner_id)
            db.delete(stale)
            if stale_owner is not None:
                db.delete(stale_owner)
        now = datetime.now(UTC)
        new_user = User(display_name=args.name)
        db.add(new_user)
        db.flush()
        template = Workspace(
            owner_id=new_user.id,
            name=args.name,
            slug=f"sample-{uuid.uuid4().hex[:8]}",
            whatsapp=normalise_number(args.whatsapp),
            is_template=True,
            consent_account_at=now,
            consent_recording_at=now,
        )
        db.add(template)
        db.flush()
        user_id, ws_id = new_user.id, template.id

    job_ids: list[uuid.UUID] = []
    for video in args.videos:
        with factory.begin() as db:
            ws = db.get(Workspace, ws_id)
            if ws is None:
                raise SystemExit("sample shop disappeared")
            key = f"ws/{ws.id}/uploads/{uuid.uuid4().hex}.video"
            dest = storage.path(key)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(video, dest)
            with dest.open("rb") as fh:
                container = sniff_container(fh.read(16))
            try:
                if container is None:
                    raise MediaRejectedError("not_a_video", "not a video")
                info = probe(dest, MediaRules())
            except MediaRejectedError as exc:
                print(f"{video.name}: rejected ({exc})", file=sys.stderr)
                dest.unlink(missing_ok=True)
                continue
            upload = Upload(
                workspace_id=ws.id,
                storage_key=key,
                size_bytes=dest.stat().st_size,
                sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
                container=info.container,
                duration_s=info.duration_s,
            )
            db.add(upload)
            db.flush()
            new_job = create_job(db, ws, upload, "script:seed_demo", enqueue=False)
            job_ids.append(new_job.id)
        print(f"{video.name}: processing...", flush=True)
        try:
            run_pipeline_job(factory, settings, storage, str(job_ids[-1]))
        except PermanentTaskError as exc:
            print(f"{video.name}: failed ({exc})", file=sys.stderr)

    for n, job_id in enumerate(job_ids):
        with factory.begin() as db:
            job = db.get(Job, job_id)
            ws = db.get(Workspace, ws_id)
            user = db.get(User, user_id)
            if job is None or ws is None or user is None:
                raise SystemExit("sample shop disappeared")
            products = db.scalars(select(Product).where(Product.job_id == job.id)).all()
            flags = db.scalars(
                select(FlagRow).where(FlagRow.job_id == job.id, FlagRow.status == "open")
            ).all()
            print(f"\nvideo {n + 1}: {job.status}, ${job.cost_usd}")
            for p in products:
                print(f"  {p.idx}. {p.title_en}: {p.price_inr}")
            for f in flags:
                print(f"  ? {f.kind} (item {f.product_idx})")
            if n >= publish_count or job.status != "needs_review":
                continue
            by_idx = {p.idx: p for p in products}
            for f in flags:
                target = by_idx.get(f.product_idx) if f.product_idx is not None else None
                if target is not None and target.price_inr is None:
                    target.removed = True
                    f.status, f.resolution = "resolved", {"action": "remove_item"}
                else:
                    f.status, f.resolution = "dismissed", {"action": "dismiss"}
            db.flush()
            catalog = publish_job(db, settings, storage, ws, user, job)
            print(f"  published as shop version {catalog.version}")
    print("\nSample shop ready: demo visitors get a copy when they pick 'Try the sample shop'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
