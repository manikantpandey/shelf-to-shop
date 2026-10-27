"""Application settings, read from environment variables (and .env in development)."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from engine.config import EngineConfig, ModelIds, SpendCaps

AppMode = Literal["standalone", "socialpulse"]
# demo: production security settings, but demo login allowed and a visible banner (hackathon).
Environment = Literal["dev", "test", "demo", "prod"]

# Integration plugins are loaded by module path, so the core never imports them statically.
INTEGRATION_PLUGINS: dict[str, str] = {"socialpulse": "integrations.socialpulse.plugin"}
DEV_SECRET = "dev-only-secret-do-not-use-outside-your-laptop"  # noqa: S105  (refused outside dev/test)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    app_mode: AppMode = "standalone"
    environment: Environment = "dev"
    log_level: str = "INFO"

    database_url: str = "sqlite:///./storage/shelf.db"
    public_base_url: str = "http://localhost:5173"
    # Where this API is reached, if not the same origin as the site (dev, native shell).
    api_base_url: str | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Shortcut sign-in for dev and the hackathon demo; refused when ENVIRONMENT=prod.
    demo_login_enabled: bool = False

    # Where uploads, job work files and published media live (local disk in dev).
    storage_dir: str = "./storage"
    # Run queued jobs inside the API process (dev convenience; production runs a worker).
    worker_inline: bool = False
    # Session cookie lifetime.
    session_hours: int = 24 * 14
    # Server secret for hashing session tokens; must be set (32+ chars) outside dev and test.
    secret_key: SecretStr = SecretStr(DEV_SECRET)
    # Labelled clip the fake providers replay (PROVIDERS=fake).
    fake_scenario: str = "evals/labels/synth_a.json"

    providers: Literal["meta", "fake"] = "meta"
    text_llm_provider: Literal["meta", "baseten"] = "meta"
    meta_api_key: SecretStr | None = None
    meta_api_base_url: str = "https://api.meta.ai/v1"
    meta_vision_model: str = "muse-spark-1.3"
    meta_segment_model: str = "sam-3.1"
    meta_transcribe_model: str = "muse-voice-transcribe-1.0"
    meta_image_model: str = "muse-image-1.0"
    baseten_api_key: SecretStr | None = None
    baseten_base_url: str = "https://inference.baseten.co/v1"
    baseten_model_id: str = "meta-models/muse-spark-open"

    # Open Food Facts asks callers to identify themselves: "AppName/Version (contact)".
    openfoodfacts_enabled: bool = True
    openfoodfacts_user_agent: str = (
        "ShelfToShop/0.1 (https://github.com/manikantpandey/shelf-to-shop)"
    )

    spend_cap_per_job_usd: Decimal = Decimal("0.50")
    spend_cap_per_workspace_day_usd: Decimal = Decimal("3.00")
    spend_cap_per_instance_day_usd: Decimal = Decimal("25.00")

    @model_validator(mode="after")
    def check_production_safety(self) -> Settings:
        if self.environment in ("demo", "prod"):
            if not self.public_base_url.startswith("https://"):
                raise ValueError("PUBLIC_BASE_URL must be https outside dev and test")
            key = self.secret_key.get_secret_value()
            if key == DEV_SECRET or len(key) < 32:
                raise ValueError("SECRET_KEY must be set to 32+ random characters")
        if self.environment == "prod":
            if self.demo_login_enabled:
                raise ValueError("DEMO_LOGIN_ENABLED must be false in production")
            if self.providers == "fake":
                raise ValueError("PROVIDERS=fake is not allowed in production")
        if self.demo_login_enabled and self.app_mode != "standalone":
            raise ValueError("demo login is only available in standalone mode")
        return self

    @property
    def api_url(self) -> str:
        return (self.api_base_url or self.public_base_url).rstrip("/")

    @property
    def secure_cookies(self) -> bool:
        return self.environment in ("demo", "prod")

    def engine_config(self) -> EngineConfig:
        return EngineConfig(
            providers=self.providers,
            text_provider=self.text_llm_provider,
            meta_api_key=self.meta_api_key,
            meta_base_url=self.meta_api_base_url,
            baseten_api_key=self.baseten_api_key,
            baseten_base_url=self.baseten_base_url,
            models=ModelIds(
                vision=self.meta_vision_model,
                segment=self.meta_segment_model,
                transcribe=self.meta_transcribe_model,
                image=self.meta_image_model,
                baseten_text=self.baseten_model_id,
            ),
            caps=SpendCaps(
                per_job_usd=self.spend_cap_per_job_usd,
                per_workspace_day_usd=self.spend_cap_per_workspace_day_usd,
                per_instance_day_usd=self.spend_cap_per_instance_day_usd,
            ),
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
