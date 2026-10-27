"""Outbound HTTP with a host allowlist: the engine can only reach hosts it was configured for."""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

import httpx


class OutboundHostNotAllowedError(httpx.TransportError):
    pass


class AllowlistTransport(httpx.AsyncBaseTransport):
    def __init__(self, allowed_hosts: Iterable[str], inner: httpx.AsyncBaseTransport | None = None):
        self.allowed = frozenset(h.lower() for h in allowed_hosts)
        self.inner = inner or httpx.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host.lower()
        if request.url.scheme != "https" or host not in self.allowed:
            raise OutboundHostNotAllowedError(
                f"outbound request to {request.url.scheme}://{host} is not allowed"
            )
        return await self.inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self.inner.aclose()


def host_of(url: str) -> str:
    host = urlsplit(url).hostname
    if not host:
        raise ValueError(f"not an absolute URL: {url}")
    return host


def allowlisted_client(
    base_url: str,
    headers: dict[str, str],
    *,
    timeout_s: float,
    extra_hosts: Iterable[str] = (),
    inner: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    transport = AllowlistTransport([host_of(base_url), *extra_hosts], inner=inner)
    return httpx.AsyncClient(
        base_url=base_url,
        headers=headers,
        timeout=httpx.Timeout(timeout_s, connect=15.0),
        transport=transport,
        follow_redirects=False,
    )
