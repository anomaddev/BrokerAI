"""AI Strategy instrument constraints: one symbol, one owner per pair."""

from __future__ import annotations

import pytest

from brokerai.ai_strategy.instruments import (
    ai_strategy_owns_instrument,
    default_ai_strategy_name,
    resolve_ai_strategy_name,
    validate_ai_strategy_instrument_selection,
)
from brokerai.db.repositories.strategies import StrategiesRepository
from brokerai.strategies.presets.ai_strategy.definition import DEFAULT_PARAMS


pytestmark = pytest.mark.usefixtures("sqlite_db")


def test_validate_requires_exactly_one_forex_symbol():
    assert validate_ai_strategy_instrument_selection({"forex": ["USD/JPY"]}) == "USD/JPY"

    with pytest.raises(ValueError, match="exactly one instrument"):
        validate_ai_strategy_instrument_selection({"forex": ["EUR/USD", "USD/JPY"]})

    with pytest.raises(ValueError, match="exactly one instrument"):
        validate_ai_strategy_instrument_selection({})

    with pytest.raises(ValueError, match="forex-only"):
        validate_ai_strategy_instrument_selection({"metals": ["XAU/USD"]})


def test_ai_strategy_owns_instrument():
    doc = {
        "preset_id": "ai_strategy",
        "instruments": ["USD/JPY"],
        "instrument_selection": {"forex": ["USD/JPY"]},
    }
    assert ai_strategy_owns_instrument(doc, "USD/JPY") is True
    assert ai_strategy_owns_instrument(doc, "EUR/USD") is False
    assert ai_strategy_owns_instrument({"preset_id": "ema_crossover"}, "USD/JPY") is False


def test_default_ai_strategy_name():
    assert default_ai_strategy_name("USD/JPY") == "AI Strategy - USD/JPY"
    assert resolve_ai_strategy_name("", "EUR/USD") == "AI Strategy - EUR/USD"
    assert resolve_ai_strategy_name("AI Strategy", "EUR/USD") == "AI Strategy - EUR/USD"
    assert resolve_ai_strategy_name("My custom name", "EUR/USD") == "My custom name"


@pytest.mark.asyncio
async def test_create_applies_default_name_from_instrument():
    created = await _create_ai(name="AI Strategy", instrument_selection={"forex": ["GBP/USD"]})
    assert created["name"] == "AI Strategy - GBP/USD"


async def _create_ai(**overrides):
    repo = StrategiesRepository()
    payload = {
        "name": "AI USDJPY",
        "description": "",
        "preset_id": "ai_strategy",
        "params": dict(DEFAULT_PARAMS),
        "instrument_selection": {"forex": ["USD/JPY"]},
    }
    payload.update(overrides)
    return await repo.create(**payload)


@pytest.mark.asyncio
async def test_create_ai_strategy_single_instrument():
    created = await _create_ai()
    assert created["instruments"] == ["USD/JPY"]
    assert created["instrument_selection"] == {"forex": ["USD/JPY"]}
    assert created["enabled"] is True
    assert created["execution_phase"] == "warming"


@pytest.mark.asyncio
async def test_create_ai_strategy_forces_enabled_even_if_client_passes_false():
    created = await _create_ai(enabled=False)
    assert created["enabled"] is True


@pytest.mark.asyncio
async def test_create_rejects_multiple_instruments():
    with pytest.raises(ValueError, match="exactly one instrument"):
        await _create_ai(instrument_selection={"forex": ["EUR/USD", "USD/JPY"]})


@pytest.mark.asyncio
async def test_create_rejects_duplicate_instrument_owner():
    await _create_ai(name="First")
    with pytest.raises(ValueError, match="already has an AI Strategy"):
        await _create_ai(name="Second", instrument_selection={"forex": ["USD/JPY"]})


@pytest.mark.asyncio
async def test_update_rejects_taking_another_ai_instruments_symbol():
    first = await _create_ai(name="First", instrument_selection={"forex": ["USD/JPY"]})
    second = await _create_ai(name="Second", instrument_selection={"forex": ["EUR/USD"]})
    repo = StrategiesRepository()
    with pytest.raises(ValueError, match="already has an AI Strategy"):
        await repo.update(second["id"], instrument_selection={"forex": ["USD/JPY"]})
    # Same strategy may keep its own symbol.
    kept = await repo.update(first["id"], instrument_selection={"forex": ["USD/JPY"]})
    assert kept is not None
    assert kept["instruments"] == ["USD/JPY"]


@pytest.mark.asyncio
async def test_find_ai_strategy_for_instrument():
    created = await _create_ai()
    repo = StrategiesRepository()
    found = await repo.find_ai_strategy_for_instrument("USD/JPY")
    assert found is not None
    assert found["id"] == created["id"]
    assert await repo.find_ai_strategy_for_instrument("EUR/USD") is None
    assert (
        await repo.find_ai_strategy_for_instrument(
            "USD/JPY",
            exclude_strategy_id=created["id"],
        )
        is None
    )
