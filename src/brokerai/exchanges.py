from __future__ import annotations

ASSET_CLASSES = ("forex", "metals", "stocks", "crypto", "futures", "options")

EXCHANGES: dict[str, dict] = {
    "oanda": {
        "name": "OANDA",
        "asset_classes": ("forex", "metals"),
    },
    "ibkr": {
        "name": "Interactive Brokers",
        "asset_classes": ("forex", "metals", "stocks", "crypto", "futures", "options"),
    },
    "metatrader5": {
        "name": "MetaTrader 5",
        "asset_classes": ("forex",),
    },
    "binance": {
        "name": "Binance",
        "asset_classes": ("crypto",),
    },
    "coinbase": {
        "name": "Coinbase",
        "asset_classes": ("crypto",),
    },
    "kraken": {
        "name": "Kraken",
        "asset_classes": ("crypto",),
    },
}

EXCHANGE_IDS = frozenset(EXCHANGES)


def exchanges_for_asset_class(asset_class: str) -> list[str]:
    if asset_class not in ASSET_CLASSES:
        raise ValueError(f"Unknown asset class: {asset_class}")
    return sorted(
        exchange_id
        for exchange_id, meta in EXCHANGES.items()
        if asset_class in meta["asset_classes"]
    )


def validate_primary_exchange(asset_class: str, exchange_id: str | None) -> str | None:
    if not exchange_id:
        return None
    if exchange_id not in EXCHANGE_IDS:
        raise ValueError(f"Unknown exchange: {exchange_id}")
    if asset_class not in EXCHANGES[exchange_id]["asset_classes"]:
        raise ValueError(f"Exchange {exchange_id} does not support asset class {asset_class}")
    return exchange_id
