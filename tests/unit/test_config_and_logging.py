from __future__ import annotations

import pytest
from pydantic import ValidationError

from engine.config import ModelIds
from shelf.config import Settings
from shelf.core.ids import uuid7
from shelf.core.logging import REDACTED, scrub_processor, scrub_text


def _settings(**kw: object) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[call-arg, arg-type]


def test_contributor_models_are_refused() -> None:
    with pytest.raises(ValidationError, match="contributor"):
        ModelIds(vision="muse-spark-1.3-contributor")


def test_contributor_models_refused_via_settings() -> None:
    with pytest.raises(ValidationError):
        _settings(meta_vision_model="muse-spark-1.2-contributor").engine_config()


def test_demo_login_refused_in_production() -> None:
    with pytest.raises(ValidationError, match="DEMO_LOGIN_ENABLED"):
        _settings(environment="prod", demo_login_enabled=True)


def test_fake_providers_refused_in_production() -> None:
    with pytest.raises(ValidationError, match="PROVIDERS=fake"):
        _settings(environment="prod", providers="fake")


def test_demo_login_only_in_standalone() -> None:
    with pytest.raises(ValidationError, match="standalone"):
        _settings(demo_login_enabled=True, app_mode="socialpulse")


# Fake keys are assembled at runtime so the secret scanner's rules stay strict for real files.
FAKE_META_KEY = "_".join(["LLM", "1607358788850350", "fakefakefakefakefake"])
FAKE_OUR_KEY = "_".join(["sts", "live", "ab12cd34"]) + "." + "f" * 40


def test_engine_config_carries_secrets_as_secretstr() -> None:
    cfg = _settings(meta_api_key=FAKE_META_KEY).engine_config()
    assert cfg.meta_api_key is not None
    assert "fakefake" not in repr(cfg)


@pytest.mark.parametrize(
    "raw",
    [
        f"key {FAKE_META_KEY} here",
        "Authorization: Bearer abc.def.ghi",
        "mail seller@example.com now",
        "call +91 98765 43210",
        "call 9876543210",
        f"api key {FAKE_OUR_KEY}",
    ],
)
def test_scrub_text_redacts_secrets_and_pii(raw: str) -> None:
    assert REDACTED in scrub_text(raw)


def test_scrub_text_keeps_prices_and_ids() -> None:
    text = "matched price 1200 for product 3 at 12.5s"
    assert scrub_text(text) == text


def test_scrub_processor_redacts_keys_and_nested_values() -> None:
    event = {
        "event": "x",
        "authorization": "Bearer t",
        "meta": {"email": "a@b.co", "note": FAKE_META_KEY},
    }
    out = scrub_processor(None, "info", event)
    assert out["authorization"] == REDACTED
    assert out["meta"]["email"] == REDACTED
    assert out["meta"]["note"] == REDACTED


def test_uuid7_is_versioned_and_time_ordered() -> None:
    ids = [uuid7() for _ in range(50)]
    assert all(i.version == 7 for i in ids)
    assert [i.int >> 80 for i in ids] == sorted(i.int >> 80 for i in ids)
