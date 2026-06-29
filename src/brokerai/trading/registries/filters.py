from __future__ import annotations

from typing import Any, Protocol

from brokerai.trading.indicator_cache import IndicatorCacheView


class FilterEvaluator(Protocol):
    filter_type: str

    def evaluate(
        self,
        filter_spec: dict[str, Any],
        candles: list[dict[str, Any]],
        indicators: IndicatorCacheView,
        direction: str | None,
    ) -> tuple[bool, dict[str, Any]]: ...


_FILTERS: dict[str, FilterEvaluator] = {}


def register_filter(filter_type: str, evaluator: FilterEvaluator) -> None:
    _FILTERS[filter_type] = evaluator


def get_filter_evaluator(filter_type: str) -> FilterEvaluator | None:
    return _FILTERS.get(filter_type)


def run_filter_chain(
    filters: list[dict[str, Any]],
    candles: list[dict[str, Any]],
    indicators: IndicatorCacheView,
    direction: str | None,
) -> tuple[bool, dict[str, dict[str, Any]]]:
    results: dict[str, dict[str, Any]] = {}
    passed = True

    for filter_spec in filters:
        if not isinstance(filter_spec, dict):
            continue
        if not filter_spec.get("enabled", True):
            filter_id = str(filter_spec.get("id", "unknown"))
            results[filter_id] = {"passed": True, "skipped": True}
            continue

        filter_type = str(filter_spec.get("type", ""))
        filter_id = str(filter_spec.get("id", filter_type))
        evaluator = get_filter_evaluator(filter_type)
        if evaluator is None:
            results[filter_id] = {"passed": True, "unknown_type": filter_type}
            continue

        filter_passed, metadata = evaluator.evaluate(filter_spec, candles, indicators, direction)
        results[filter_id] = {"passed": filter_passed, **metadata}
        if not filter_passed:
            passed = False

    return passed, results
