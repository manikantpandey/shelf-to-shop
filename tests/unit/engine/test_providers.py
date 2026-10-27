from __future__ import annotations

import json
import random
from decimal import Decimal

import httpx
import pytest

from engine.config import SpendCaps
from engine.net import AllowlistTransport, OutboundHostNotAllowedError
from engine.providers.errors import (
    CircuitOpenError,
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderBillingError,
    ProviderGatewayTimeoutError,
    ProviderRateLimitedError,
    ProviderStreamError,
    ProviderUnavailableError,
    classify_response,
)
from engine.providers.meta_client import MetaClient, output_text, usage_tokens
from engine.providers.resilience import CallStats, CircuitBreaker, Resilient, RetryPolicy
from engine.spend import (
    InMemorySpendLedger,
    SpendCapExceededError,
    sam_video_cost,
    spark_cost,
    transcribe_cost,
)

pytestmark = pytest.mark.anyio


def _err(status: int, code: str = "x", headers: dict[str, str] | None = None) -> httpx.Response:
    body = {"error": {"message": "nope", "type": "t", "param": None, "code": code}}
    return httpx.Response(status, json=body, headers=headers or {})


@pytest.mark.parametrize(
    ("status", "kind", "retryable"),
    [
        (400, ProviderBadRequestError, False),
        (401, ProviderAuthError, False),
        (402, ProviderBillingError, False),
        (403, ProviderAuthError, False),
        (404, ProviderBadRequestError, False),
        (413, ProviderBadRequestError, False),
        (429, ProviderRateLimitedError, True),
        (500, ProviderUnavailableError, True),
        (503, ProviderUnavailableError, True),
        (504, ProviderGatewayTimeoutError, False),
    ],
)
def test_classify_response(status: int, kind: type, retryable: bool) -> None:
    err = classify_response("meta", _err(status))
    assert isinstance(err, kind)
    assert err.retryable is retryable
    assert err.status == status


def test_retry_after_is_read() -> None:
    err = classify_response("meta", _err(429, headers={"retry-after": "15"}))
    assert err.retry_after_s == 15.0


def test_backoff_respects_retry_after_and_cap() -> None:
    policy = RetryPolicy(base_delay_s=1, max_delay_s=4)
    rng = random.Random(1)
    assert all(policy.delay_s(a, None, rng) <= 4 for a in range(10))
    assert policy.delay_s(0, 30.0, rng) == 30.0


class _Flaky:
    def __init__(self, errors: list[Exception], result: str = "ok") -> None:
        self.errors = errors
        self.result = result
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return self.result


def _resilient(**kw: object) -> tuple[Resilient, list[float]]:
    slept: list[float] = []

    async def fake_sleep(s: float) -> None:
        slept.append(s)

    return Resilient("meta", sleep=fake_sleep, rng=random.Random(0), **kw), slept  # type: ignore[arg-type]


async def test_retries_transient_errors_then_succeeds() -> None:
    r, slept = _resilient()
    fn = _Flaky([ProviderUnavailableError("down", provider="meta")] * 2)
    stats = CallStats()
    assert await r.call(fn, stats) == "ok"
    assert fn.calls == 3
    assert stats.attempts == 3
    assert len(slept) == 2


async def test_does_not_retry_bad_requests() -> None:
    r, slept = _resilient()
    fn = _Flaky([ProviderBadRequestError("bad", provider="meta")])
    with pytest.raises(ProviderBadRequestError):
        await r.call(fn)
    assert fn.calls == 1
    assert slept == []


async def test_gateway_timeout_is_not_retried() -> None:
    r, _ = _resilient()
    fn = _Flaky([ProviderGatewayTimeoutError("slow", provider="meta")])
    with pytest.raises(ProviderGatewayTimeoutError):
        await r.call(fn)
    assert fn.calls == 1


async def test_gives_up_when_retry_after_is_too_long() -> None:
    r, slept = _resilient()
    fn = _Flaky([ProviderRateLimitedError("slow down", provider="meta", retry_after_s=600)])
    with pytest.raises(ProviderRateLimitedError):
        await r.call(fn)
    assert slept == []


async def test_stops_after_max_retries() -> None:
    r, _ = _resilient(policy=RetryPolicy(max_retries=2))
    fn = _Flaky([ProviderUnavailableError("down", provider="meta")] * 5)
    with pytest.raises(ProviderUnavailableError):
        await r.call(fn)
    assert fn.calls == 3


async def test_network_errors_become_unavailable() -> None:
    r, _ = _resilient(policy=RetryPolicy(max_retries=0))

    async def boom() -> str:
        raise httpx.ConnectError("refused")

    with pytest.raises(ProviderUnavailableError, match="network error"):
        await r.call(boom)


def test_circuit_breaker_opens_and_half_opens() -> None:
    now = [0.0]
    b = CircuitBreaker("meta", failure_threshold=2, reset_timeout_s=10, clock=lambda: now[0])
    b.before_call()
    b.record_failure()
    b.record_failure()
    assert b.state == "open"
    with pytest.raises(CircuitOpenError):
        b.before_call()
    now[0] = 11
    assert b.state == "half_open"
    b.before_call()  # one trial allowed
    with pytest.raises(CircuitOpenError):
        b.before_call()  # second concurrent trial refused
    b.record_success()
    assert b.state == "closed"


async def test_breaker_ignores_client_errors() -> None:
    breaker = CircuitBreaker("meta", failure_threshold=1)
    r, _ = _resilient(breaker=breaker)
    with pytest.raises(ProviderBadRequestError):
        await r.call(_Flaky([ProviderBadRequestError("bad", provider="meta")]))
    assert breaker.state == "closed"


def test_spend_prices() -> None:
    assert spark_cost(1_000_000, 0) == Decimal("1.25")
    assert spark_cost(1_000_000, 0, cached_input_tokens=1_000_000) == Decimal("0.15")
    assert sam_video_cost(10) == sam_video_cost(50) == Decimal("0.01")
    assert transcribe_cost(3600) == Decimal("0.18")


def test_ledger_enforces_job_and_day_caps() -> None:
    ledger = InMemorySpendLedger(SpendCaps(per_job_usd=Decimal("0.10")))
    res = ledger.reserve("job1", "ws1", Decimal("0.08"))
    ledger.settle(res, Decimal("0.05"))
    assert ledger.spent_on_job("job1") == Decimal("0.05")
    with pytest.raises(SpendCapExceededError) as exc:
        ledger.reserve("job1", "ws1", Decimal("0.06"))
    assert exc.value.scope == "job"
    ledger.reserve("job2", "ws1", Decimal("0.06"))  # other job unaffected


async def test_allowlist_blocks_other_hosts_and_plain_http() -> None:
    inner = httpx.MockTransport(lambda req: httpx.Response(200, json={}))
    async with httpx.AsyncClient(transport=AllowlistTransport(["api.meta.ai"], inner)) as c:
        assert (await c.get("https://api.meta.ai/v1/x")).status_code == 200
        with pytest.raises(OutboundHostNotAllowedError):
            await c.get("https://169.254.169.254/latest/meta-data")
        with pytest.raises(OutboundHostNotAllowedError):
            await c.get("http://api.meta.ai/v1/x")


def _meta(handler: object) -> MetaClient:
    return MetaClient("test-key", transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


async def test_create_response_sends_bearer_and_parses_output() -> None:
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "OK"}]}],
                "usage": {"input_tokens": 10, "output_tokens": 3},
            },
        )

    async with _meta(handler) as client:
        body = await client.create_response({"model": "muse-spark-1.3", "input": "hi"})
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"] == {"model": "muse-spark-1.3", "input": "hi", "stream": False}
    assert output_text(body) == "OK"
    assert usage_tokens(body) == (10, 3, 0)


async def test_errors_are_classified() -> None:
    async with _meta(lambda req: _err(429, headers={"retry-after": "2"})) as client:
        with pytest.raises(ProviderRateLimitedError):
            await client.create_response({"model": "m", "input": "x"})


async def test_stream_raises_on_failed_event() -> None:
    sse = (
        'data: {"type":"response.output_text.delta","delta":"<0f>"}\n\n'
        'data: {"type":"response.failed","response":{"status":"failed",'
        '"error":{"code":"server_error","message":"boom"}}}\n\n'
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    events = []
    async with _meta(handler) as client:
        with pytest.raises(ProviderStreamError, match="boom"):
            async for event in client.stream_response({"model": "sam-3.1", "input": []}):
                events.append(event)
    assert [e["type"] for e in events] == ["response.output_text.delta"]


async def test_upload_sends_purpose_and_expiry_before_file() -> None:
    seen: dict[str, bytes] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = req.content
        return httpx.Response(200, json={"id": "file-1"})

    async with _meta(handler) as client:
        assert await client.upload_file(b"\x00\x01", "v.mp4", "video/mp4") == "file-1"
    body = seen["body"]
    assert body.index(b'name="purpose"') < body.index(b'name="file"')
    assert b"expires_after[seconds]" in body
    assert b"3600" in body
