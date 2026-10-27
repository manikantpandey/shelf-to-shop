"""Engine configuration.

The engine never reads environment variables or the app's settings directly; the caller builds an
`EngineConfig` and passes it in, so the engine works from the API worker, the CLI and tests.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

ProviderKind = Literal["meta", "fake"]
TextProviderKind = Literal["meta", "baseten"]


class ModelIds(BaseModel):
    model_config = ConfigDict(frozen=True)

    vision: str = "muse-spark-1.3"
    segment: str = "sam-3.1"
    transcribe: str = "muse-voice-transcribe-1.0"
    image: str = "muse-image-1.0"
    baseten_text: str = "meta-models/muse-spark-open"

    @field_validator("*")
    @classmethod
    def refuse_contributor_models(cls, value: str) -> str:
        # Contributor variants let Meta train on submitted content; videos can show customers.
        if "contributor" in value.lower():
            raise ValueError(f"contributor model ids are not allowed: {value}")
        return value


class SpendCaps(BaseModel):
    model_config = ConfigDict(frozen=True)

    per_job_usd: Decimal = Field(default=Decimal("0.50"), gt=0)
    per_workspace_day_usd: Decimal = Field(default=Decimal("3.00"), gt=0)
    per_instance_day_usd: Decimal = Field(default=Decimal("25.00"), gt=0)


class EngineConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    providers: ProviderKind = "meta"
    text_provider: TextProviderKind = "meta"
    meta_api_key: SecretStr | None = None
    meta_base_url: str = "https://api.meta.ai/v1"
    baseten_api_key: SecretStr | None = None
    baseten_base_url: str = "https://inference.baseten.co/v1"
    models: ModelIds = ModelIds()
    caps: SpendCaps = SpendCaps()
    # Seconds a single provider call may take before we give up on it.
    request_timeout_s: float = Field(default=120.0, gt=0)
    max_retries: int = Field(default=3, ge=0, le=8)
