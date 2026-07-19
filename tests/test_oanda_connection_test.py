from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from brokerai.integrations.oanda import test_connection as oanda_test_connection
from brokerai.integrations.oanda_client import normalize_access_token


def test_normalize_access_token_strips_paste_artifacts():
    raw = "  Bearer abc\u200b123–\ndef  "
    assert normalize_access_token(raw) == "abc123-def"


@pytest.mark.asyncio
async def test_oanda_connection_suggests_alternate_environment_on_auth_mismatch():
    practice_response = httpx.Response(401, json={"errorMessage": "Insufficient authorization"})
    practice_error = httpx.HTTPStatusError(
        "unauthorized",
        request=httpx.Request("GET", "https://api-fxpractice.oanda.com/v3/accounts"),
        response=practice_response,
    )

    with patch(
        "brokerai.integrations.oanda.list_accounts",
        new=AsyncMock(
            side_effect=[
                practice_error,
                [{"id": "101-001-1-001", "tags": []}],
            ]
        ),
    ) as list_accounts:
        ok, message, accounts, suggested, diagnostics = await oanda_test_connection(
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "practice",
        )

    assert ok is True
    assert suggested == "live"
    assert accounts == [{"id": "101-001-1-001", "tags": []}]
    assert "Live" in message
    assert diagnostics["environments_tried"] == ["practice", "live"]
    assert list_accounts.await_count == 2


@pytest.mark.asyncio
async def test_oanda_connection_reports_both_environments_failed():
    unauthorized = httpx.HTTPStatusError(
        "unauthorized",
        request=httpx.Request("GET", "https://api-fxpractice.oanda.com/v3/accounts"),
        response=httpx.Response(401, json={"errorMessage": "Insufficient authorization"}),
    )

    with patch(
        "brokerai.integrations.oanda.list_accounts",
        new=AsyncMock(side_effect=[unauthorized, unauthorized]),
    ):
        ok, message, accounts, suggested, diagnostics = await oanda_test_connection(
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "practice",
        )

    assert ok is False
    assert suggested is None
    assert accounts == []
    assert "Tools → API" in message
    assert diagnostics["token_length"] == 64


@pytest.mark.asyncio
async def test_oanda_connection_rejects_incomplete_token_shape():
    ok, message, accounts, suggested, diagnostics = await oanda_test_connection(
        "V6T2x4o5E02cmptq8J44UuW3P6js2pjo", "practice"
    )
    assert ok is False
    assert accounts == []
    assert suggested is None
    assert "two halves" in message
    assert diagnostics["token_length"] == 32
