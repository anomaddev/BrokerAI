from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from brokerai.integrations.oanda import _fetch_paginated_transactions


@pytest.mark.asyncio
async def test_fetch_paginated_transactions_follows_pages():
    http = MagicMock()
    http.get_json = AsyncMock(
        side_effect=[
            {
                "transactions": [{"id": "1", "type": "ORDER_FILL", "time": "2026-07-01T00:00:00.000000000Z"}],
                "pages": ["https://api-fxpractice.oanda.com/v3/accounts/acc/transactions/idrange?page=2"],
                "lastTransactionID": "2",
            },
            {
                "transactions": [{"id": "2", "type": "DAILY_FINANCING", "time": "2026-07-02T00:00:00.000000000Z"}],
                "lastTransactionID": "2",
            },
        ]
    )

    events, last_txn = await _fetch_paginated_transactions(
        http,
        initial_path="/v3/accounts/acc/transactions/idrange",
        params={"from": "1", "to": "2"},
    )

    assert len(events) == 2
    assert last_txn == "2"
    assert http.get_json.await_count == 2
    http.get_json.assert_any_await(
        "https://api-fxpractice.oanda.com/v3/accounts/acc/transactions/idrange?page=2",
        timeout=30.0,
    )


@pytest.mark.asyncio
async def test_iter_transaction_pages_yields_per_page_batches():
    from brokerai.integrations.oanda import _iter_transaction_pages

    http = MagicMock()
    http.get_json = AsyncMock(
        side_effect=[
            {
                "transactions": [{"id": "1", "type": "ORDER_FILL", "time": "2026-07-01T00:00:00.000000000Z"}],
                "pages": ["https://api-fxpractice.oanda.com/v3/accounts/acc/transactions/idrange?page=2"],
            },
            {
                "transactions": [{"id": "2", "type": "DAILY_FINANCING", "time": "2026-07-02T00:00:00.000000000Z"}],
            },
        ]
    )

    pages: list[list[dict]] = []
    async for batch in _iter_transaction_pages(
        http,
        initial_path="/v3/accounts/acc/transactions/idrange",
        params={"from": "1", "to": "2"},
    ):
        pages.append(batch)

    assert len(pages) == 2
    assert pages[0][0]["id"] == "1"
    assert pages[1][0]["id"] == "2"
