"""Thin async client for the Meta Model API (https://dev.meta.ai/docs).

Only request shapes documented on dev.meta.ai are used. Errors are classified into typed
ProviderErrors; retries and circuit breaking live in `Resilient`, one level up.
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from engine.net import allowlisted_client
from engine.providers.errors import (
    ProviderBadRequestError,
    ProviderStreamError,
    classify_response,
)

PROVIDER = "meta"
# Meta Files: shortest allowed expiry; we also delete files explicitly after each stage.
FILE_EXPIRY_S = 3600


def output_text(body: dict[str, Any]) -> str:
    """Concatenate the `output_text` parts of a Responses API body."""
    return "".join(
        part.get("text", "")
        for item in body.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    )


def usage_tokens(body: dict[str, Any]) -> tuple[int, int, int]:
    """(input_tokens, output_tokens, cached_input_tokens) from a Responses API body."""
    usage = body.get("usage") or {}
    cached = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
    return usage.get("input_tokens", 0), usage.get("output_tokens", 0), cached


class MetaClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.meta.ai/v1",
        *,
        timeout_s: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._http = allowlisted_client(
            base_url,
            {"Authorization": f"Bearer {api_key}"},
            timeout_s=timeout_s,
            inner=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> MetaClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def _json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = await self._http.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise classify_response(PROVIDER, response)
        if not response.content:
            return {}
        data: dict[str, Any] = response.json()
        return data

    # --- Responses API -------------------------------------------------------------------
    async def create_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = await self._json("POST", "/responses", json={**payload, "stream": False})
        if body.get("status") == "failed":
            err = body.get("error") or {}
            raise ProviderStreamError(
                err.get("message", "response failed"), provider=PROVIDER, code=err.get("code")
            )
        return body

    async def get_response(self, response_id: str) -> dict[str, Any]:
        return await self._json("GET", f"/responses/{response_id}")

    async def stream_response(self, payload: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """Yield SSE events; raise on `response.failed` or `error` terminal events."""
        async with self._http.stream(
            "POST", "/responses", json={**payload, "stream": True}
        ) as response:
            if response.status_code >= 400:
                await response.aread()
                raise classify_response(PROVIDER, response)
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                event: dict[str, Any] = json.loads(data)
                kind = event.get("type")
                if kind == "response.failed":
                    err = (event.get("response") or {}).get("error") or {}
                    raise ProviderStreamError(
                        err.get("message", "response failed"),
                        provider=PROVIDER,
                        code=err.get("code"),
                    )
                if kind == "error":
                    raise ProviderStreamError(
                        event.get("message", "stream error"),
                        provider=PROVIDER,
                        code=event.get("code"),
                    )
                yield event

    # --- Files API -----------------------------------------------------------------------
    async def upload_file(
        self, data: bytes, filename: str, mime: str, expires_after_s: int = FILE_EXPIRY_S
    ) -> str:
        if not 3600 <= expires_after_s <= 2_592_000:
            raise ProviderBadRequestError("expires_after must be 1 h to 30 d", provider=PROVIDER)
        # Docs: send purpose and expires_after before the file part for lower upload latency.
        fields = {
            "purpose": "user_data",
            "expires_after[anchor]": "created_at",
            "expires_after[seconds]": str(expires_after_s),
        }
        body = await self._json(
            "POST", "/files", data=fields, files={"file": (filename, data, mime)}
        )
        file_id: str = body["id"]
        return file_id

    async def delete_file(self, file_id: str) -> None:
        await self._json("DELETE", f"/files/{file_id}")

    # --- Images --------------------------------------------------------------------------
    async def generate_image(
        self, model: str, prompt: str, *, size: str = "1024x1024", output_format: str = "png"
    ) -> bytes:
        body = await self._json(
            "POST",
            "/images/generations",
            json={
                "model": model,
                "prompt": prompt,
                "n": 1,
                "size": size,
                "output_format": output_format,
            },
        )
        return base64.b64decode(body["data"][0]["b64_json"])

    # --- Speech to text --------------------------------------------------------------------
    async def transcribe(self, wav: bytes, request: dict[str, Any]) -> dict[str, Any]:
        files = {
            "request": (None, json.dumps(request), "application/json"),
            "audio": ("audio.wav", wav, "audio/wav"),
        }
        return await self._json(
            "POST", "/asr/transcribe", files=files, headers={"Accept": "application/json"}
        )
