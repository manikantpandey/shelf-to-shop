from __future__ import annotations

import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from shelf.config import Settings
from shelf.plugins import PluginUnavailableError, load_integration


def test_health_reports_mode_and_version(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["mode"] == "standalone"


def test_ready_checks_database(client: TestClient) -> None:
    assert client.get("/api/v1/health/ready").json() == {"status": "ready"}


def test_request_id_is_generated_and_echoed(client: TestClient) -> None:
    generated = client.get("/api/v1/health").headers["x-request-id"]
    assert len(generated) >= 8
    supplied = "abcd1234-req"
    assert (
        client.get("/api/v1/health", headers={"x-request-id": supplied}).headers["x-request-id"]
        == supplied
    )


def test_malformed_request_id_is_replaced(client: TestClient) -> None:
    r = client.get("/api/v1/health", headers={"x-request-id": "bad id\n<script>"})
    assert r.headers["x-request-id"] != "bad id\n<script>"


def test_unknown_route_returns_problem_json(client: TestClient) -> None:
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["code"] == "not_found"
    assert body["request_id"] == r.headers["x-request-id"]


class _Payload(BaseModel):
    email: str
    count: int


def test_validation_errors_do_not_echo_input(settings: Settings) -> None:
    from shelf.main import create_app

    app = create_app(settings)

    @app.post("/echo")
    def echo(payload: _Payload) -> dict[str, str]:
        return {"ok": "yes"}

    with TestClient(app) as c:
        r = c.post("/echo", json={"email": "seller@example.com", "count": "many"})
    assert r.status_code == 422
    assert r.json()["code"] == "validation_failed"
    assert "seller@example.com" not in r.text
    assert "many" not in r.text


def test_unhandled_errors_hide_internals(settings: Settings) -> None:
    from shelf.main import create_app

    app = create_app(settings)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("database password is hunter2")

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/boom")
    assert r.status_code == 500
    assert r.json()["code"] == "internal_error"
    assert "hunter2" not in r.text


def test_standalone_mode_loads_no_plugin(settings: Settings) -> None:
    assert load_integration(FastAPI(), settings) is None


def test_plugin_is_loaded_by_module_path(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    fake = types.ModuleType("fake_plugin")
    fake.register = lambda app, s: calls.append(s.app_mode)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fake_plugin", fake)
    sp = settings.model_copy(update={"app_mode": "socialpulse"})
    assert load_integration(FastAPI(), sp, {"socialpulse": "fake_plugin"}) == "fake_plugin"
    assert calls == ["socialpulse"]


def test_missing_plugin_fails_clearly(settings: Settings) -> None:
    sp = settings.model_copy(update={"app_mode": "socialpulse"})
    with pytest.raises(PluginUnavailableError, match="not in this build"):
        load_integration(FastAPI(), sp, {"socialpulse": "integrations.does_not_exist"})
