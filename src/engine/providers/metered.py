"""Run a provider call with a spend reservation, resilience and a run-log entry."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from engine.providers.errors import (
    CircuitOpenError,
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderBillingError,
    ProviderError,
    ProviderRateLimitedError,
)
from engine.providers.resilience import CallStats, Resilient
from engine.runlog import CallContext, RunLogEntry

# Failures the provider rejects before doing any work: nothing to pay for.
_UNBILLED = (
    ProviderBadRequestError,
    ProviderAuthError,
    ProviderBillingError,
    ProviderRateLimitedError,
    CircuitOpenError,
)


@dataclass(frozen=True)
class Usage:
    cost_usd: Decimal
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class Metered[T]:
    value: T
    usage: Usage
    latency_ms: int
    attempts: int


async def metered_call[T](
    ctx: CallContext,
    resilient: Resilient,
    *,
    provider: str,
    model: str,
    operation: str,
    estimate_usd: Decimal,
    fn: Callable[[], Awaitable[T]],
    usage_of: Callable[[T], Usage],
    inputs_summary: dict[str, Any] | None = None,
    outputs_summary: Callable[[T], dict[str, Any]] | None = None,
) -> Metered[T]:
    """Reserve `estimate_usd` (raises SpendCapExceededError first), call, settle actual cost."""
    reservation = ctx.ledger.reserve(ctx.job_id, ctx.workspace_id, estimate_usd)
    stats = CallStats()
    try:
        value = await resilient.call(fn, stats)
    except ProviderError as exc:
        charged = Decimal(0) if isinstance(exc, _UNBILLED) else estimate_usd
        ctx.ledger.settle(reservation, charged)
        ctx.runlog.record(
            RunLogEntry(
                job_id=ctx.job_id,
                stage=ctx.stage,
                provider=provider,
                model=model,
                operation=operation,
                latency_ms=stats.latency_ms,
                attempts=stats.attempts,
                cost_usd=charged,
                inputs_summary=inputs_summary or {},
                error=str(exc),
            )
        )
        raise
    usage = usage_of(value)
    ctx.ledger.settle(reservation, usage.cost_usd)
    ctx.runlog.record(
        RunLogEntry(
            job_id=ctx.job_id,
            stage=ctx.stage,
            provider=provider,
            model=model,
            operation=operation,
            latency_ms=stats.latency_ms,
            attempts=stats.attempts,
            cost_usd=usage.cost_usd,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            inputs_summary=inputs_summary or {},
            outputs_summary=outputs_summary(value) if outputs_summary else {},
        )
    )
    return Metered(value, usage, stats.latency_ms, stats.attempts)
