from __future__ import annotations

import time

import httpx
import pytest

from brokerai.integrations.oanda_client import (
    OandaHttpClient,
    _ConnectionGate,
    _TokenBucket,
    close_oanda_client,
)


@pytest.mark.asyncio
async def test_token_bucket_limits_rate():
    bucket = _TokenBucket(10.0)
    start = time.monotonic()
    for _ in range(3):
        await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.5


@pytest.mark.asyncio
async def test_oanda_client_reuses_connection(monkeypatch):
    calls = 0

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            pass

        async def request(self, method, url, **kwargs):
            nonlocal calls
            calls += 1
            req = httpx.Request(method, url)
            return httpx.Response(200, json={"ok": True}, request=req)

        async def aclose(self):
            return None

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    client = OandaHttpClient(
        environment="practice",
        access_token="test-token",
        request_limiter=_TokenBucket(100),
        connection_gate=_ConnectionGate(2),
    )
    await client.get_json("/v3/accounts")
    await client.get_json("/v3/accounts")
    assert calls == 2
    await client.close()


@pytest.mark.asyncio
async def test_close_oanda_client_clears_singleton():
    from brokerai.integrations import oanda_client as oc

    stub = OandaHttpClient(
        environment="practice",
        access_token="x",
        request_limiter=_TokenBucket(10),
        connection_gate=_ConnectionGate(2),
    )
    oc._CLIENTS[("practice", "abc")] = stub
    await close_oanda_client()
    assert oc._CLIENTS == {}
