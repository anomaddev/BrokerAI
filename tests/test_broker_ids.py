from __future__ import annotations

import pytest

from brokerai.trading.broker.ids import (
    broker_event_key,
    broker_lot_key,
    parse_broker_event_key,
    parse_broker_lot_key,
)


def test_broker_lot_key_round_trip():
    key = broker_lot_key("oanda", "565")
    assert key == "oanda:565"
    assert parse_broker_lot_key(key) == ("oanda", "565")


def test_broker_event_key_round_trip():
    key = broker_event_key("oanda", "566")
    assert parse_broker_event_key(key) == ("oanda", "566")


def test_parse_invalid_key_raises():
    with pytest.raises(ValueError):
        parse_broker_lot_key("invalid")
