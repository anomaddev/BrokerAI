from tests.fixtures.mock_candles import generate_mock_candles
from brokerai.trading.indicators.adx import compute_adx
from brokerai.trading.indicators.atr import compute_atr
from brokerai.trading.indicators.ema import compute_ema


def test_compute_ema_warmup_length():
    candles = generate_mock_candles(50)
    ema = compute_ema(candles, 9)
    assert len(ema) == len(candles) - 9 + 1


def test_compute_adx_returns_values():
    candles = generate_mock_candles(60)
    adx = compute_adx(candles, 14)
    assert len(adx) > 0
    assert 0 <= adx[-1]["value"] <= 60


def test_compute_atr_positive():
    candles = generate_mock_candles(30)
    atr = compute_atr(candles, 14)
    assert atr > 0
