from __future__ import annotations

import pytest

from brokerai.db.repositories.strategies import StrategiesRepository
from brokerai.db.repositories.strategy_versions import (
    MAX_VERSIONS_PER_STRATEGY,
    StrategyVersionsRepository,
    append_strategy_version,
    strategy_version_snapshot,
)
from brokerai.db.pg.client import session_scope
from brokerai.strategies.presets.ema_crossover.definition import DEFAULT_PARAMS


pytestmark = pytest.mark.usefixtures("sqlite_db")


async def _create_strategy(**overrides):
    repo = StrategiesRepository()
    payload = {
        "name": "Versioned EMA",
        "description": "notes",
        "preset_id": "ema_crossover",
        "params": dict(DEFAULT_PARAMS),
        "instrument_selection": {"forex": ["EUR/USD"]},
        "enabled": False,
    }
    payload.update(overrides)
    return await repo.create(**payload)


@pytest.mark.asyncio
async def test_create_writes_version_one():
    created = await _create_strategy()
    versions, total = await StrategyVersionsRepository().list_for_strategy(created["id"])
    assert total == 1
    assert versions[0]["version"] == 1
    assert versions[0]["change_label"] == "Created strategy"

    detail = await StrategyVersionsRepository().get_by_id(created["id"], versions[0]["id"])
    assert detail is not None
    assert detail["snapshot"]["name"] == "Versioned EMA"
    assert detail["snapshot"]["params"]["timeframe"] == "M15"


@pytest.mark.asyncio
async def test_definition_update_appends_version_enabled_only_does_not():
    repo = StrategiesRepository()
    created = await _create_strategy()

    updated = await repo.update(created["id"], name="Renamed EMA")
    assert updated is not None
    versions, total = await StrategyVersionsRepository().list_for_strategy(created["id"])
    assert total == 2
    assert versions[0]["version"] == 2
    assert "renamed" in versions[0]["change_label"].lower()

    await repo.update(created["id"], enabled=True)
    versions_after_toggle, total_after_toggle = await StrategyVersionsRepository().list_for_strategy(
        created["id"]
    )
    assert total_after_toggle == 2
    assert versions_after_toggle[0]["version"] == 2


@pytest.mark.asyncio
async def test_delete_strategy_removes_versions():
    repo = StrategiesRepository()
    created = await _create_strategy()
    await repo.update(created["id"], description="changed")

    deleted = await repo.delete(created["id"])
    assert deleted is True
    versions, total = await StrategyVersionsRepository().list_for_strategy(created["id"])
    assert total == 0
    assert versions == []


@pytest.mark.asyncio
async def test_prune_keeps_latest_max_versions():
    created = await _create_strategy()
    async with session_scope() as session:
        for i in range(MAX_VERSIONS_PER_STRATEGY + 5):
            await append_strategy_version(
                session,
                strategy_id=created["id"],
                snapshot=strategy_version_snapshot(
                    {
                        "name": f"v{i}",
                        "description": "",
                        "params": {},
                        "instrument_selection": {"forex": ["EUR/USD"]},
                        "enabled": False,
                        "preset_id": "ema_crossover",
                    }
                ),
                change_label=f"Update {i}",
            )

    versions, total = await StrategyVersionsRepository().list_for_strategy(
        created["id"],
        limit=100,
    )
    assert total == MAX_VERSIONS_PER_STRATEGY
    assert len(versions) == MAX_VERSIONS_PER_STRATEGY
    assert versions[0]["version"] == MAX_VERSIONS_PER_STRATEGY + 6  # create + 55 appends, pruned
    assert versions[-1]["version"] == versions[0]["version"] - MAX_VERSIONS_PER_STRATEGY + 1


@pytest.mark.asyncio
async def test_strategy_version_snapshot_fields():
    snap = strategy_version_snapshot(
        {
            "name": "A",
            "description": "B",
            "params": {"timeframe": "H1"},
            "instrument_selection": {"forex": ["GBP/USD"]},
            "enabled": True,
            "preset_id": "custom",
            "stats": {"total_trades": 9},
        }
    )
    assert snap == {
        "name": "A",
        "description": "B",
        "params": {"timeframe": "H1"},
        "instrument_selection": {"forex": ["GBP/USD"]},
        "enabled": True,
        "preset_id": "custom",
    }
