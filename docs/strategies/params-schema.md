# Strategy Params Schema (v1)

BrokerAI stores strategy configuration in Postgres (`brokerai.strategies`) as a JSONB `doc` whose `params` field is a structured **StrategyParams v1** object. Every preset (EMA Crossover today, others later) uses the same top-level sections. Presets differ by which indicator types, signal types, and filter types they populate inside those sections—not by inventing new top-level keys.

Access is via the FastAPI app only: schema `brokerai` is not exposed to Supabase PostgREST (`anon` / `authenticated`). RLS is enabled with no policies as deny-by-default defense in depth.

## Why sections?

- **Shared execution and risk** — sessions, confidence, position sizing work the same across strategies.
- **Composable filters** — filters are an ordered list; new filter types plug in without schema migrations.
- **Indicator references** — signals reference named indicators by id, so presets can use different indicator sets.
- **Versioned migration** — `schema_version` enables safe upgrades when the shape evolves.

## Top-level shape

```json
{
  "schema_version": 1,
  "timeframe": "M15",
  "additional_timeframes": ["H1", "H4"],
  "min_candles": 63,
  "indicators": { },
  "signal": { },
  "filters": [ ],
  "exits": { },
  "risk": { },
  "execution": { }
}
```

### Standard sections

| Section | Type | Purpose |
|---------|------|---------|
| `schema_version` | `integer` | Must be `1`. Increment on breaking changes. |
| `timeframe` | `string` | Primary bar interval (`M1`…`MN`; see constants) |
| `additional_timeframes` | `string[]` | Optional extra TFs to fetch (must not include primary) |
| `min_candles` | `integer` | Warm-up bars required before the strategy runs |
| `indicators` | `object` | Map of logical id → indicator spec |
| `signal` | `object` | Entry logic; `type` discriminates preset signal |
| `filters` | `array` | Ordered AND chain of filter specs |
| `exits` | `object` | Stop loss, take profit, trailing stop |
| `risk` | `object` | Position sizing and trade caps |
| `execution` | `object` | Sessions and confidence threshold |

### Naming rules

- Sections and fields: **snake_case**
- Indicator map keys: stable ids (`fast`/`slow` for legacy defaults, or builder component ids like `ema_*`)
- Filter items: stable `id` + `type` discriminator
- Signal references indicators via `*_ref` fields
- Percent fields: suffix `_pct` (e.g. `risk_per_trade_pct`)
- Multiplier fields: suffix `_multiplier`
- Booleans: `enabled` inside filter/trailing objects

### What does **not** belong in `params`

| Field | Stored on |
|-------|-----------|
| Instrument assignment | Strategy document `instrument_selection` |
| Strategy on/off | Strategy document `enabled` |
| Chart UI overlays | Frontend only (not persisted) |

---

## Section reference

### `timeframe`

Shared bar interval for the strategy.

| Value | Meaning |
|-------|---------|
| `M5` | 5 minutes |
| `M15` | 15 minutes |
| `M30` | 30 minutes |
| `H1` | 1 hour |
| `H4` | 4 hours |
| `D1` | 1 day |

### `indicators`

Map of **id → spec**. Each spec has a `type` discriminator.

#### `ema`

| Field | Type | Default | Bounds |
|-------|------|---------|--------|
| `type` | `"ema"` | required | — |
| `period` | integer | — | preset-specific (EMA: fast 3–50, slow 10–200) |
| `source` | string | `"close"` | `close`, `open`, `high`, `low`, `hl2`, `hlc3`, `ohlc4` |
| `color` | string | omitted | Optional chart color (UI-only; ignored by the engine) |

#### `sma`

Same fields as `ema` with `type: "sma"` (including optional `color`).

#### `rsi`

| Field | Type | Default |
|-------|------|---------|
| `type` | `"rsi"` | required |
| `period` | integer | — |
| `source` | string | `"close"` |
| `overbought` | number | `70` |
| `oversold` | number | `30` |

### `signal`

Entry logic. The `type` field selects the signal evaluator.

#### `ema_crossover`

| Field | Type | Description |
|-------|------|-------------|
| `type` | `"ema_crossover"` | Discriminator |
| `fast_ref` | string | Key in `indicators` for fast EMA |
| `slow_ref` | string | Key in `indicators` for slow EMA |
| `direction` | string | `long`, `short`, or `both` |
| `confirmation` | string | `close`, `pullback`, or `aggressive` |

**Cross-field rule:** `indicators[fast_ref].period` must be less than `indicators[slow_ref].period`.

### `filters`

Ordered array. All **enabled** filters must pass (logical AND).

#### `adx`

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Stable id (e.g. `"adx"`) |
| `type` | `"adx"` | Discriminator |
| `enabled` | boolean | Toggle filter |
| `period` | integer | ADX lookback (7–28) |
| `threshold` | number | Level to compare (15–40) |
| `compare` | string | `gte`, `lte`, `gt`, `lt`, `eq` |

#### `atr`

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Stable id (e.g. `"atr"`) |
| `type` | `"atr"` | Discriminator |
| `enabled` | boolean | Toggle filter |
| `period` | integer | ATR lookback (7–28) |
| `min_value` | number | Optional minimum ATR |
| `max_value` | number | Optional maximum ATR |

#### `rsi` (reserved)

| Field | Type | Description |
|-------|------|-------------|
| `id`, `type`, `enabled`, `period` | — | Same pattern as above |
| `min_value`, `max_value` | number | Optional RSI bounds |

#### `custom` (future)

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Stable id |
| `type` | `"custom"` | Discriminator |
| `enabled` | boolean | Toggle filter |
| `expression` | string | Filter expression (evaluator TBD) |

### `exits`

#### `stop_loss`

| Field | Type | Values |
|-------|------|--------|
| `mode` | string | `fixed_pips`, `atr_based`, `structure` |
| `atr_multiplier` | number | Used when `mode` is `atr_based` |
| `fixed_pips` | integer | Used when `mode` is `fixed_pips` |
| `structure_lookback` | integer | Used when `mode` is `structure` |

#### `take_profit`

| Field | Type | Values |
|-------|------|--------|
| `mode` | string | `fixed_pips`, `rr_ratio`, `atr_based`, `reverse_crossover`, `trailing_stop` |
| `risk_reward_ratio` | number | Used when `mode` is `rr_ratio` |
| `fixed_pips` | integer | Used when `mode` is `fixed_pips` |
| `atr_multiplier` | number | Used when `mode` is `atr_based` |
| `trail_mode` | string | `ema_slow` or `atr` when `mode` is `trailing_stop` |
| `trail_atr_multiplier` | number | Used when `trail_mode` is `atr` |
| `trail_ema_ref` | string | Indicator ref when `trail_mode` is `ema_slow` |

`reverse_crossover` and `trail_mode: ema_slow` require `signal.type` of `ema_crossover`.

### `risk`

| Field | Type | Bounds |
|-------|------|--------|
| `risk_per_trade_pct` | number | 0.25–5.0 (% of account) |
| `max_trades_per_day` | integer | 1–20 |

### `min_candles`

| Field | Type | Bounds | Description |
|-------|------|--------|-------------|
| `min_candles` | integer | computed–2000 | Minimum bars required before strategy runs on next candle; defaults to computed warm-up |

### `execution`

| Field | Type | Description |
|-------|------|-------------|
| `sessions` | string[] | At least one session name (e.g. `London`, `NY`) |
| `min_confidence` | integer | 0–100 minimum signal confidence |
| `override_all_strategies` | boolean | When true, this strategy takes priority over other enabled strategies on overlapping instruments (default `false`) |
| `priority` | integer | 0–100; lower value = higher priority (default `50`) |

Note: `max_trades_per_day` is stored under `risk` but displayed in the Execution UI section.

---

## Strategy document (Postgres)

Rows live in `brokerai.strategies` with denormalized columns (`id`, `asset_class`, `name`, `enabled`, `preset_id`) plus a JSONB `doc` containing the full strategy document (including `params`):

```json
{
  "id": "<uuid hex>",
  "name": "My EMA Strategy",
  "description": "...",
  "asset_class": "forex",
  "enabled": false,
  "instruments": ["EUR/USD"],
  "instrument_selection": { "forex": ["EUR/USD"] },
  "strategy_type": "preset",
  "preset_id": "ema_crossover",
  "route": "/research/strategies/new/ema-crossover",
  "params": { },
  "params_schema_version": 1,
  "stats": { },
  "created_at": "...",
  "updated_at": "..."
}
```

One-shot repair for docs written before indicator replace-merge:

`./venv/bin/python scripts/cleanup_strategy_orphan_indicators.py --dry-run`

---

## API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/strategies/presets` | List presets with `default_params` and `param_schema` |
| GET | `/api/strategies` | List saved strategies (includes `params`) |
| POST | `/api/strategies` | Create; params validated and merged with preset defaults |
| GET | `/api/strategies/{id}` | Single strategy |
| PATCH | `/api/strategies/{id}` | Partial update |
| DELETE | `/api/strategies/{id}` | Delete |

Validation errors return HTTP 400 with a descriptive message.

---

## Code locations

| Layer | Path |
|-------|------|
| Params package | `src/brokerai/strategies/params/` |
| Preset definitions | `src/brokerai/strategies/presets/` |
| Registry | `src/brokerai/strategies/registry.py` |
| Repository | `src/brokerai/db/repositories/strategies.py` |
| API routes | `src/brokerai/web/routes/strategies.py` |
| Frontend types | `frontend/src/lib/strategyParams/` |
| EMA mapper | `frontend/src/pages/strategies/presets/emaCrossover/apiParams.ts` |

---

## Adding a new preset

1. **Backend definition** — Create `src/brokerai/strategies/presets/<name>/definition.py` with v1 `DEFAULT_PARAMS`, `PARAM_SCHEMA`, and `StrategyPreset` (include `route`, `signal_type`).
2. **Signal validator** — Add validation in `src/brokerai/strategies/params/validate.py` for the new `signal.type`.
3. **Registry** — Register in `src/brokerai/strategies/registry.py`.
4. **Frontend preset card** — Add to `frontend/src/pages/strategies/presets/index.ts`.
5. **Frontend mapper** — Add `*ParamsToV1()` and optional `v1To*Params()` in the preset folder.
6. **Documentation** — Append signal/filter sections to this file.

---

## Schema version policy

BrokerAI expects **v1 sectioned params** (`schema_version: 1`). Flat snake_case legacy keys and `exits.trailing` are rejected on read/write with a validation error. Increment `schema_version` and update this document when making breaking param changes.
