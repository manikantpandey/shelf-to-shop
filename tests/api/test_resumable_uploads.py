"""Resumable uploads: pieces in order, carrying on after a drop, the final check, and isolation."""

from __future__ import annotations

import shutil
from typing import Any

import pytest
from fastapi.testclient import TestClient

from shelf.config import Settings
from shelf.main import create_app

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _seller(c: TestClient, name: str = "Upload Shop") -> dict[str, str]:
    assert c.post("/api/v1/auth/demo", json={"shop_name": name}).status_code == 200
    h = {"x-csrf-token": c.cookies["sts_csrf"]}
    c.post("/api/v1/consents/recording", headers=h)
    return h


def _piece(c: TestClient, h: dict[str, str], uid: str, offset: int, data: bytes) -> Any:
    return c.patch(f"/api/v1/uploads/{uid}", content=data,
                   headers={**h, "upload-offset": str(offset),
                            "content-type": "application/octet-stream"})  # fmt: skip


def test_upload_in_pieces_and_carry_on_after_a_drop(
    app_and_client: tuple[Any, TestClient], clip: bytes
) -> None:
    _, c = app_and_client
    h = _seller(c)
    r = c.post("/api/v1/uploads/sessions", json={"size": len(clip)}, headers=h)
    assert r.status_code == 201, r.text
    session = r.json()
    uid, size = session["id"], len(clip)
    assert session["status"] == "receiving" and session["offset"] == 0 and session["chunk_size"] > 0

    third = size // 3
    r = _piece(c, h, uid, 0, clip[:third])
    assert r.json() == {**r.json(), "status": "receiving", "offset": third}

    # A job cannot start from half a video.
    r = c.post("/api/v1/jobs", json={"upload_id": uid}, headers=h)
    assert r.status_code == 409 and r.json()["code"] == "not_ready"

    # The connection dropped and the phone retried from the wrong place: told where to carry on.
    r = _piece(c, h, uid, 0, clip[:third])
    assert r.status_code == 409 and r.json()["code"] == "offset_mismatch"
    assert r.json()["offset"] == third
    assert c.get(f"/api/v1/uploads/{uid}").json()["offset"] == third

    r = _piece(c, h, uid, third, clip[third : 2 * third])
    assert r.json()["offset"] == 2 * third
    r = _piece(c, h, uid, 2 * third, clip[2 * third :])
    assert r.status_code == 200, r.text
    done = r.json()
    assert done["status"] == "ready" and done["offset"] == size
    assert done["duration_s"] == pytest.approx(8, abs=0.5) and done["needs_clip"] is False

    # A retried last piece after success is harmless.
    assert _piece(c, h, uid, 2 * third, clip[2 * third :]).json()["status"] == "ready"
    r = c.post("/api/v1/jobs", json={"upload_id": uid}, headers=h)
    assert r.status_code == 201, r.text


def test_pieces_cannot_overflow_or_smuggle_a_non_video(
    app_and_client: tuple[Any, TestClient],
) -> None:
    _, c = app_and_client
    h = _seller(c)
    uid = c.post("/api/v1/uploads/sessions", json={"size": 2000}, headers=h).json()["id"]
    r = _piece(c, h, uid, 0, b"x" * 2001)
    assert r.status_code == 413
    r = _piece(c, h, uid, 0, b"not a video " * 166 + b"xxxx" + b"y" * 4)
    assert r.status_code == 422 and r.json()["code"] == "not_a_video"
    assert c.get(f"/api/v1/uploads/{uid}").json()["status"] == "rejected"
    assert c.post("/api/v1/uploads/sessions", json={"size": 300 * 1024 * 1024},
                  headers=h).status_code == 422  # fmt: skip


def test_uploads_belong_to_one_shop(app_settings: Settings, clip: bytes) -> None:
    app = create_app(app_settings)
    with TestClient(app) as owner, TestClient(app) as intruder:
        h = _seller(owner)
        uid = owner.post("/api/v1/uploads/sessions", json={"size": len(clip)},
                         headers=h).json()["id"]  # fmt: skip
        hi = _seller(intruder, "Other Shop")
        assert intruder.get(f"/api/v1/uploads/{uid}").status_code == 404
        assert _piece(intruder, hi, uid, 0, clip[:100]).status_code == 404
        assert owner.get(f"/api/v1/uploads/{uid}").json()["offset"] == 0
