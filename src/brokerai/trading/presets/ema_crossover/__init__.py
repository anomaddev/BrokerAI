from brokerai.trading.presets.ema_crossover.filters import register_ema_crossover_filters
from brokerai.trading.presets.ema_crossover.exits import register_ema_crossover_exits
from brokerai.trading.presets.ema_crossover.signal import register_ema_crossover_signal


def register_ema_crossover() -> None:
    register_ema_crossover_signal()
    register_ema_crossover_filters()
    register_ema_crossover_exits()
