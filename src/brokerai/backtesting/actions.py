"""Human-readable action event builders for backtest step-through."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _bar_time(candle: dict[str, Any] | None) -> str | None:
    if not candle:
        return None
    return str(candle.get("time") or "") or None


def _confidence_pct(confidence: float) -> int:
    return int(round(float(confidence) * 100))


def build_signal_actions(
    analysis: Any,
    candle: dict[str, Any],
    *,
    sequence_start: int,
    gate_passed: bool,
    gate_reasons: list[str],
    gate_details: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build action rows from a live-parity analysis + gate evaluation."""
    actions: list[dict[str, Any]] = []
    seq = sequence_start
    meta_base = {
        "direction": analysis.direction,
        "confidence": analysis.confidence,
        "signal": (analysis.metadata or {}).get("signal"),
    }
    signal = (analysis.metadata or {}).get("signal")
    filters = (analysis.metadata or {}).get("filters") or {}
    filters_passed = bool((analysis.metadata or {}).get("filters_passed", True))
    bar_time = _bar_time(candle)

    if signal and signal != "none" and "approach" not in str(signal):
        conf = _confidence_pct(analysis.confidence)
        signal_text = str(signal)
        if signal_text.startswith("playbook_"):
            direction_label = signal_text.removeprefix("playbook_").replace("_", " ")
            signal_phrase = f"Playbook {direction_label} signal"
        else:
            signal_phrase = "Crossover detected"
        if not filters_passed:
            failed = []
            if isinstance(filters, dict):
                for fid, detail in filters.items():
                    if isinstance(detail, dict) and not detail.get("passed", True) and not detail.get(
                        "skipped"
                    ):
                        failed.append(str(fid).upper())
            filter_label = ", ".join(failed) if failed else "filter"
            actions.append(
                {
                    "sequence": seq,
                    "kind": "filter_fail",
                    "message": f"{signal_phrase}, failed {filter_label} filter",
                    "bar_time": bar_time,
                    "meta": {**meta_base, "filters": filters},
                    "created_at": datetime.now(timezone.utc),
                }
            )
            seq += 1
            return actions

        if not gate_passed:
            if "closed_on_signal" in gate_reasons:
                actions.append(
                    {
                        "sequence": seq,
                        "kind": "signal",
                        "message": (
                            f"{signal_phrase}, confidence {conf}%, "
                            "skipped — closed prior position on this signal"
                        ),
                        "bar_time": bar_time,
                        "meta": {**meta_base, "gate_reasons": gate_reasons},
                        "created_at": datetime.now(timezone.utc),
                    }
                )
            elif "confidence_below_threshold" in gate_reasons:
                detail = gate_details.get("confidence_below_threshold") or {}
                min_c = detail.get("min_confidence_pct", "?")
                actions.append(
                    {
                        "sequence": seq,
                        "kind": "signal",
                        "message": (
                            f"{signal_phrase}, confidence {conf}% "
                            f"below minimum {min_c}% — skipping trade"
                        ),
                        "bar_time": bar_time,
                        "meta": {**meta_base, "gate_reasons": gate_reasons},
                        "created_at": datetime.now(timezone.utc),
                    }
                )
            else:
                reason = ", ".join(gate_reasons) if gate_reasons else "gates"
                actions.append(
                    {
                        "sequence": seq,
                        "kind": "signal",
                        "message": f"{signal_phrase}, blocked by {reason}",
                        "bar_time": bar_time,
                        "meta": {**meta_base, "gate_reasons": gate_reasons},
                        "created_at": datetime.now(timezone.utc),
                    }
                )
            seq += 1
            return actions

        actions.append(
            {
                "sequence": seq,
                "kind": "signal",
                "message": f"{signal_phrase}, confidence {conf}%, executing trade",
                "bar_time": bar_time,
                "meta": meta_base,
                "created_at": datetime.now(timezone.utc),
            }
        )
        seq += 1

    return actions


def build_entry_action(
    *,
    sequence: int,
    candle: dict[str, Any],
    direction: str,
    price: float,
    units: float,
) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "kind": "entry",
        "message": f"Entered {direction} @ {price:.5f} ({units:g} units)",
        "bar_time": _bar_time(candle),
        "meta": {"direction": direction, "price": price, "units": units},
        "created_at": datetime.now(timezone.utc),
    }


def build_exit_action(
    *,
    sequence: int,
    candle: dict[str, Any],
    reason: str,
    price: float,
    pnl: float,
) -> dict[str, Any]:
    kind = "exit"
    if reason in {"stop_loss", "sl"}:
        kind = "sl"
        message = f"Stop Loss hit, closing position @ {price:.5f} (PnL {pnl:+.2f})"
    elif reason in {"take_profit", "tp"}:
        kind = "tp"
        message = f"Take Profit hit, closing position @ {price:.5f} (PnL {pnl:+.2f})"
    elif reason == "reverse_crossover":
        message = f"Reverse Crossover detected, closing position @ {price:.5f} (PnL {pnl:+.2f})"
    else:
        message = f"Closed position ({reason}) @ {price:.5f} (PnL {pnl:+.2f})"
    return {
        "sequence": sequence,
        "kind": kind,
        "message": message,
        "bar_time": _bar_time(candle),
        "meta": {"reason": reason, "price": price, "realized_pnl": pnl},
        "created_at": datetime.now(timezone.utc),
    }
