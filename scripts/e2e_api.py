"""Start an isolated API for browser tests: temp database, fake providers, inline worker.

Writes a test clip and its labels to web/e2e/.fixtures/ so the browser test can upload it.
Run: uv run python scripts/e2e_api.py   (Playwright starts it for you)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "web" / "e2e" / ".fixtures"

LABELS = {
    "video": "clip.mp4",
    "products": [
        {"n": 1, "what": "blue cotton saree", "appears_s": [0.0, 3.0], "spoken_price_inr": 1200,
         "spoken_at_s": 1.0, "spoken_end_s": 2.0, "spoken_words": "ye neela wala barah sau",
         "tag_price_inr": None},
        {"n": 2, "what": "red silk saree", "appears_s": [2.5, 6.0], "spoken_price_inr": 850,
         "spoken_at_s": 4.0, "spoken_end_s": 5.0, "spoken_words": "laal wala saadhe aath sau",
         # Said above the printed price: a real conflict the seller must settle.
         "tag_price_inr": 800},
        {"n": 3, "what": "pink chiffon saree", "appears_s": [5.5, 8.0], "spoken_price_inr": None,
         "spoken_at_s": None, "spoken_end_s": None, "spoken_words": "aur ye gulabi wala",
         "tag_price_inr": None},
    ],
}  # fmt: skip


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    clip = FIXTURES / "clip.mp4"
    if not clip.exists():
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise SystemExit("ffmpeg is required for the browser test clip")
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
                str(clip),
            ],
            check=True,
        )
    labels = FIXTURES / "labels.json"
    labels.write_text(json.dumps(LABELS), encoding="utf-8")

    tmp = Path(tempfile.mkdtemp(prefix="sts-e2e-"))
    env = {
        **os.environ,
        "ENVIRONMENT": "test",
        "DATABASE_URL": f"sqlite:///{(tmp / 'e2e.db').as_posix()}",
        "STORAGE_DIR": str(tmp / "storage"),
        "PROVIDERS": "fake",
        "FAKE_SCENARIO": str(labels),
        "DEMO_LOGIN_ENABLED": "true",
        "WORKER_INLINE": "true",
        "PUBLIC_BASE_URL": "http://localhost:5173",
        "API_BASE_URL": "http://localhost:8000",
        "CORS_ORIGINS": '["http://localhost:5173"]',
        "META_API_KEY": "",
    }
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True)  # noqa: S607
    # A blocking child (not exec): on Windows exec would end this process and the test runner
    # would think the server died.
    raise SystemExit(
        subprocess.call(
            ["uv", "run", "uvicorn", "--factory", "shelf.main:create_app", "--port", "8000"],  # noqa: S607
            cwd=ROOT,
            env=env,
        )
    )


if __name__ == "__main__":
    main()
