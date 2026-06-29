from brokerai.trading.work_plan import build_work_plan


def _strategy(strategy_id: str, timeframe: str, *, slow_period: int = 21) -> dict:
    return {
        "id": strategy_id,
        "name": f"Strategy {strategy_id}",
        "timeframe": timeframe,
        "params": {
            "indicators": {"slow": {"type": "ema", "period": slow_period, "source": "close"}},
            "signal": {"type": "ema_crossover"},
        },
    }


def test_build_work_plan_groups_by_timeframe_and_pair():
    strategies = [
        (_strategy("a", "M15", slow_period=21), ["EUR/USD", "GBP/USD"]),
        (_strategy("b", "M15", slow_period=50), ["EUR/USD"]),
        (_strategy("c", "H1", slow_period=21), ["EUR/USD"]),
    ]
    plan = build_work_plan(strategies)

    assert len(plan.units) == 3
    m15_eur = next(unit for unit in plan.units if unit.timeframe == "M15" and unit.pair == "EUR/USD")
    assert len(m15_eur.strategies) == 2
    assert m15_eur.bar_count >= 50


def test_build_work_plan_uses_max_bar_count():
    strategies = [
        (_strategy("a", "M15", slow_period=21), ["EUR/USD"]),
        (_strategy("b", "M15", slow_period=100), ["EUR/USD"]),
    ]
    plan = build_work_plan(strategies)
    unit = plan.units[0]
    assert unit.bar_count >= 100
