"""Shared fixtures for API tests: a real-migrated SQLite app with fake providers."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from shelf.config import Settings
from shelf.main import create_app

ROOT = Path(__file__).resolve().parents[2]

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
def clip(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg is not None
    path = tmp_path_factory.mktemp("clip") / "test.mp4"
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
    return path.read_bytes()


@pytest.fixture
def app_settings(tmp_path: Path) -> Settings:
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps(LABELS), encoding="utf-8")
    db_url = f"sqlite:///{tmp_path / 'app.db'}"
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")  # the real migrations, not create_all
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        environment="test",
        database_url=db_url,
        storage_dir=str(tmp_path / "storage"),
        providers="fake",
        fake_scenario=str(labels),
        demo_login_enabled=True,
        public_base_url="https://shop.example",
    )


@pytest.fixture
def app_and_client(app_settings: Settings) -> Iterator[tuple[Any, TestClient]]:
    app = create_app(app_settings)
    with TestClient(app) as c:
        yield app, c
