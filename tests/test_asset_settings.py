from __future__ import annotations

import pytest

from brokerai.db.repositories.asset_settings import AssetSettingsRepository


pytestmark = pytest.mark.usefixtures("sqlite_db")


@pytest.mark.asyncio
async def test_toggle_enabled_preserves_enabled_pairs():
    repo = AssetSettingsRepository()
    await repo.save(
        "forex",
        enabled=False,
        enabled_pairs=["EUR/USD", "GBP/USD"],
        primary_exchange="oanda",
    )

    await repo.save("forex", enabled=True, primary_exchange="oanda")
    after_on = await repo.get("forex")
    assert after_on["enabled"] is True
    assert after_on["enabled_pairs"] == ["EUR/USD", "GBP/USD"]

    await repo.save("forex", enabled=False, primary_exchange="oanda")
    after_off = await repo.get("forex")
    assert after_off["enabled"] is False
    assert after_off["enabled_pairs"] == ["EUR/USD", "GBP/USD"]


@pytest.mark.asyncio
async def test_explicit_empty_enabled_pairs_clears_selection():
    repo = AssetSettingsRepository()
    await repo.save(
        "forex",
        enabled=False,
        enabled_pairs=["EUR/USD"],
        primary_exchange="oanda",
    )

    await repo.save(
        "forex",
        enabled=False,
        enabled_pairs=[],
        primary_exchange="oanda",
    )
    doc = await repo.get("forex")
    assert doc["enabled_pairs"] == []
