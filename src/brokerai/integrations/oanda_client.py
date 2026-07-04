from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from brokerai.config.settings import get_settings

logger = logging.getLogger(__name__)

OANDA_ENVIRONMENTS = ("practice", "live")

_BASE_URLS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}


def base_url(environment: str) -> str:
    return _BASE_URLS.get(environment, _BASE_URLS["practice"])


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token.strip()}"}

_CLIENTS: dict[tuple[str, str], "OandaHttpClient"] = {}
_CLIENTS_LOCK = asyncio.Lock()


def _token_hash(access_token: str) -> str:
    return hashlib.sha256(access_token.strip().encode()).hexdigest()[:16]


def _should_retry_oanda(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(exc, httpx.TransportError)


class _TokenBucket:
    """Async token bucket rate limiter."""

    def __init__(self, rate_per_second: float) -> None:
        self._rate = max(0.1, rate_per_second)
        self._tokens = self._rate
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
            self._last = now
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) / self._rate
                await asyncio.sleep(wait)
                self._tokens = 0.0
                self._last = time.monotonic()
            else:
                self._tokens -= 1.0


class _ConnectionGate:
    """Limits new TCP/SSL connection establishment rate."""

    def __init__(self, rate_per_second: float) -> None:
        self._bucket = _TokenBucket(rate_per_second)

    async def acquire(self) -> None:
        await self._bucket.acquire()


class OandaHttpClient:
    """Persistent OANDA REST client with keep-alive, rate limiting, and retries."""

    def __init__(
        self,
        *,
        environment: str,
        access_token: str,
        request_limiter: _TokenBucket,
        connection_gate: _ConnectionGate,
    ) -> None:
        self._environment = environment
        self._access_token = access_token
        self._request_limiter = request_limiter
        self._connection_gate = connection_gate
        self._client: httpx.AsyncClient | None = None
        self._created_at = time.monotonic()
        self._client_lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        return base_url(self._environment)

    async def _ensure_client(self, *, timeout: float) -> httpx.AsyncClient:
        settings = get_settings()
        max_age = max(60, settings.oanda_client_max_age_seconds)
        async with self._client_lock:
            age = time.monotonic() - self._created_at
            if self._client is not None and age < max_age:
                return self._client
            if self._client is not None:
                await self._client.aclose()
                self._client = None
            await self._connection_gate.acquire()
            self._client = httpx.AsyncClient(
                timeout=timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
            self._created_at = time.monotonic()
            return self._client

    async def close(self) -> None:
        async with self._client_lock:
            if self._client is not None:
                await self._client.aclose()
                self._client = None

    async def _recreate_client(self, *, timeout: float) -> httpx.AsyncClient:
        async with self._client_lock:
            if self._client is not None:
                await self._client.aclose()
                self._client = None
            await self._connection_gate.acquire()
            self._client = httpx.AsyncClient(
                timeout=timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
            self._created_at = time.monotonic()
            return self._client

    @retry(
        retry=retry_if_exception(_should_retry_oanda),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        timeout: float = 15.0,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Send an authenticated request to a relative OANDA API *path*."""
        await self._request_limiter.acquire()
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        headers = dict(auth_headers(self._access_token))
        if extra_headers:
            headers.update(extra_headers)
        if json is not None:
            headers.setdefault("Content-Type", "application/json")

        try:
            client = await self._ensure_client(timeout=timeout)
            response = await client.request(method, url, headers=headers, params=params, json=json)
            if response.status_code in (429, 500, 502, 503, 504):
                response.raise_for_status()
            return response
        except httpx.TransportError:
            await self._recreate_client(timeout=timeout)
            raise

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        response = await self.request("GET", path, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    async def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float = 15.0,
        allow_404: bool = False,
    ) -> httpx.Response:
        response = await self.request("GET", path, params=params, timeout=timeout)
        if allow_404 and response.status_code == 404:
            return response
        response.raise_for_status()
        return response


_REQUEST_LIMITER: _TokenBucket | None = None
_CONNECTION_GATE: _ConnectionGate | None = None


def _shared_request_limiter() -> _TokenBucket:
    global _REQUEST_LIMITER
    if _REQUEST_LIMITER is None:
        settings = get_settings()
        _REQUEST_LIMITER = _TokenBucket(max(1, settings.oanda_max_requests_per_second))
    return _REQUEST_LIMITER


def _shared_connection_gate() -> _ConnectionGate:
    global _CONNECTION_GATE
    if _CONNECTION_GATE is None:
        settings = get_settings()
        _CONNECTION_GATE = _ConnectionGate(max(0.5, settings.oanda_max_new_connections_per_second))
    return _CONNECTION_GATE


async def get_oanda_client(access_token: str, environment: str) -> OandaHttpClient:
    """Return a process-scoped persistent client for OANDA REST calls."""
    key = (environment, _token_hash(access_token))
    async with _CLIENTS_LOCK:
        client = _CLIENTS.get(key)
        if client is not None:
            return client
        client = OandaHttpClient(
            environment=environment,
            access_token=access_token,
            request_limiter=_shared_request_limiter(),
            connection_gate=_shared_connection_gate(),
        )
        _CLIENTS[key] = client
        return client


async def close_oanda_client() -> None:
    """Close all persistent OANDA HTTP clients (app/bot shutdown)."""
    global _REQUEST_LIMITER, _CONNECTION_GATE
    async with _CLIENTS_LOCK:
        for client in _CLIENTS.values():
            await client.close()
        _CLIENTS.clear()
    _REQUEST_LIMITER = None
    _CONNECTION_GATE = None


async def close_oanda_client_for_credentials(access_token: str, environment: str) -> None:
    """Close the client for a specific credential pair (token rotation)."""
    key = (environment, _token_hash(access_token))
    async with _CLIENTS_LOCK:
        client = _CLIENTS.pop(key, None)
    if client is not None:
        await client.close()
