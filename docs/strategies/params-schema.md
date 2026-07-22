# Strategy Params Schema (v1)

BrokerAI stores strategy configuration in Postgres (`brokerai.strategies`) as a JSONB `doc` whose `params` field is a structured **StrategyParams v1** object. Every preset (EMA Crossover, AI Strategy, Custom) uses the same top-level sections. Presets differ by which indicator types, signal types, and filter types they populate inside those sections—not by inventing new top-level keys.

For AI Strategy lifecycle (warm-up / promote / shadow), see [ai-strategy.md](./ai-strategy.md).

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
  "execution": { },
  "ai": { }
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
| `ai` | `object` | AI Strategy knobs only (model, guidance toggles, LLM cadence). Required/persisted for `ai_strategy` preset. |

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
| AI execution phase / warm-up clocks | Strategy document `execution_phase`, `warmup` (lifecycle) |
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
| `approaching` | object | Optional watch-only approaching-cross assist (see below) |

**Cross-field rule:** `indicators[fast_ref].period` must be less than `indicators[slow_ref].period`.

##### `approaching`

| Field | Type | Default | Bounds | Description |
|-------|------|---------|--------|-------------|
| `enabled` | boolean | `true` | — | Emit watch-only approaching signals when EMAs converge |
| `max_gap_atr` | number | `0.5` | 0.05–2.0 | Max `|fast − slow| / ATR` to count as approaching |
| `min_narrow_bars` | integer | `2` | 1–10 | Consecutive narrow bars required |

Approaching signals never open trades by themselves; disable to require a completed close-confirmed crossover only.

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
| `min_value` | number | Optional minimum ATR for non-JPY pairs (absolute; UI/schema max `0.5`) |
| `min_value_jpy` | number | Optional minimum ATR for JPY-quote pairs (e.g. USD/JPY); same bounds. Engine picks by pair quote currency. |
| `max_value` | number | Optional maximum ATR |

#### `htf_bias`

Require entry direction to align with a higher-timeframe EMA trend (closed bars only).

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Stable id (e.g. `"htf_bias"`) |
| `type` | `"htf_bias"` | Discriminator |
| `enabled` | boolean | Toggle filter |
| `timeframe` | string | `H1` or `H4` |

When enabled, the analyzer warms `htf_ema:{tf}:fast` / `slow` series. Missing HTF data fails closed.

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

#### `reverse_crossover`

Nested exit settings for EMA reverse-crossover protection. Always normalized for `signal.type == "ema_crossover"`. When `enabled` is true, the reverse-crossover exit monitor is attached even if `take_profit.mode` is a price-based mode.

| Field | Type | Default | Bounds | Description |
|-------|------|---------|--------|-------------|
| `enabled` | boolean | `true` | — | Master switch for reverse-crossover exits |
| `min_bars_after_entry` | integer | `6` | 0–30 | Ignore reverse exits in the first N bars after entry |
| `min_confirmation_bars` | integer | `2` | 1–5 | Reverse EMA relationship must hold for this many bars |
| `min_separation_atr` | number | `0.2` | 0–1.0 | Minimum `|fast − slow| / ATR` before accepting the reverse (`0` disables) |

Requires `signal.type` of `ema_crossover` when `enabled` is true. ATR stop loss remains the hard safety net independently of these settings.

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
| `post_stop_cooldown_bars` | integer | 0–30; block new entries for N strategy bars after a `stop_loss` exit on the same strategy+pair (default `0`) |

Note: `max_trades_per_day` is stored under `risk` but displayed in the Execution UI section.

### `ai`

AI Strategy knobs only. Required and persisted for `preset_id=ai_strategy`. Other presets omit or ignore this section. Validated by `strategies/params/ai_section.py`.

| Field | Type | Default | Bounds / values |
|-------|------|---------|-----------------|
| `model_id` | string \| null | `null` | LLM id from Settings → Models |
| `use_daily_report` | boolean | `true` | Include daily research as bias |
| `use_weekly_brief` | boolean | `true` | Include weekly brief as bias |
| `use_weekly_debrief` | boolean | `true` | Include weekly debrief as bias |
| `llm_mode` | string | `off` | `off`, `on_signal_change`, `interval`, `manual` |
| `min_llm_interval_minutes` | integer | `240` | 15–10080 |
| `max_llm_calls_per_day` | integer | `12` | 0–500 |
| `max_llm_calls_per_symbol_per_day` | integer | `4` | 0–100 |
| `max_context_bars` | integer | `64` | 16–500 |
| `learn_enabled` | boolean | `false` | Queue outcome → memory digest learning |

#### Signal types used with AI Strategy

| `signal.type` | Where used |
|---------------|------------|
| `ai_strategy` | Live / shadow analysis (`ModelSignalRuntime`) |
| `compiled_playbook` | Ephemeral docs for daily AI Strategy backtests (not edited in the builder) |

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

AI Strategy docs additionally carry lifecycle fields on the document (not inside `params`):

| Field | Purpose |
|-------|---------|
| `execution_phase` | `warming` \| `ready` \| `live` |
| `warmup` | ET trading-day warm-up counters and episode metadata |
| `ai_improve` | Daily improve queue stamp / skip reason |

Promote to live: `POST /api/strategies/{id}/promote`.

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
| POST | `/api/strategies/{id}/promote` | Promote a ready AI Strategy to `live` |

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
| AI Strategy mapper | `frontend/src/pages/strategies/presets/aiStrategy/apiParams.ts` |
| AI lifecycle / shadow | `src/brokerai/ai_strategy/` |

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
