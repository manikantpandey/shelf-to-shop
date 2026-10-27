"""Typed provider errors, classified from HTTP responses per dev.meta.ai/docs/error-handling."""

from __future__ import annotations

from typing import ClassVar

import httpx


class ProviderError(Exception):
    """Base class. `retryable` errors may succeed if the same request is sent again later."""

    retryable: ClassVar[bool] = False
    # Whether this failure says something about the provider's health (feeds the circuit breaker).
    counts_against_health: ClassVar[bool] = False

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status: int | None = None,
        code: str | None = None,
        retry_after_s: float | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status = status
        self.code = code
        self.retry_after_s = retry_after_s

    def __str__(self) -> str:
        parts = [self.provider, super().__str__()]
        if self.status:
            parts.append(f"status={self.status}")
        if self.code:
            parts.append(f"code={self.code}")
        return " ".join(parts)


class ProviderBadRequestError(ProviderError):
    """400/404/406/413/422: the request must change; never retried unchanged."""


class ProviderAuthError(ProviderError):
    """401/403: key missing, wrong, or lacking access to the model."""


class ProviderBillingError(ProviderError):
    """402: billing issue on the provider account."""


class ProviderRateLimitedError(ProviderError):
    retryable = True


class ProviderUnavailableError(ProviderError):
    """500/502/503 and network failures."""

    retryable = True
    counts_against_health = True


class ProviderTimeoutError(ProviderError):
    """Our own client-side deadline passed."""

    retryable = True
    counts_against_health = True


class ProviderGatewayTimeoutError(ProviderError):
    """504: the same request will usually time out again; resubmit in background mode instead."""

    counts_against_health = True


class ProviderStreamError(ProviderError):
    """A stream ended with `response.failed` or an `error` event."""

    retryable = True
    counts_against_health = True


class ProviderInvalidOutputError(ProviderError):
    """The model answered, but not in the shape we asked for (after the repair retry)."""


class CircuitOpenError(ProviderError):
    """We stopped calling this provider for a while after repeated failures."""


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def classify_response(provider: str, response: httpx.Response) -> ProviderError:
    """Map a non-2xx response to a typed error. Messages come from the provider's sanitised body."""
    status = response.status_code
    code: str | None = None
    message = f"HTTP {status}"
    try:
        err = response.json().get("error") or {}
        code = err.get("code") or err.get("type")
        message = err.get("message") or message
    except (ValueError, AttributeError):
        pass
    if status == 429:
        kind: type[ProviderError] = ProviderRateLimitedError
    elif status in (401, 403):
        kind = ProviderAuthError
    elif status == 402:
        kind = ProviderBillingError
    elif status == 504:
        kind = ProviderGatewayTimeoutError
    elif status >= 500:
        kind = ProviderUnavailableError
    else:
        kind = ProviderBadRequestError
    retry_after = _retry_after(response) if kind.retryable else None
    return kind(message, provider=provider, status=status, code=code, retry_after_s=retry_after)
