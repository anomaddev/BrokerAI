# AI Strategy

Model-derived forex strategy that uses research reports as **bias only**, runs a configurable **shadow warm-up**, then requires an **explicit promote to live**. It learns from trade outcomes and from at-most-daily **compiled-playbook backtests** with optional Auto AI feedback.

See also: [Strategy params schema](./params-schema.md), [The Loop](../architecture/the-loop.md), [Data Analyzer](../architecture/data-analyzer.md).

## What it is (and is not)

| Is | Is not |
|----|--------|
| First-class preset (`preset_id=ai_strategy`, `signal.type=ai_strategy`) | An EMA crossover with an LLM bolted on |
| Research (daily / weekly brief / debrief) as directional bias | Per-candle LLM on every close |
| Isolated shadow ledger during warm-up | Paper lots in `broker_lots` |
| Explicit promote after warm-up completes | Auto-promote to live |
| Daily backtests on a **compiled playbook** (no live LLM in the BT loop) | Walk-forward / multi-asset (deferred) |

Forex-only today. Other asset classes are not registered for this preset.

## Lifecycle

Lifecycle fields live on the **strategy document** (not in `params`):

| Field | Purpose |
|-------|---------|
| `execution_phase` | `warming` → `ready` → `live` |
| `warmup` | ET trading-day counters, episode id, ready/live timestamps |
| `ai_improve` | Daily improve queue stamp / skip reason |

### Phases

1. **warming** — Signals may run; intents go to `shadow_intents` / `shadow_lots` only. Warm-up advances on **realtime** closed bars during forex session (catchup/bootstrap never advances).
2. **ready** — Warm-up target met; still shadow-only. UI enables **Promote to live**.
3. **live** — Broker may dispatch Associates for this strategy (subject to normal gates and priority).

Default warm-up length is **5 ET trading days** (`Settings → Broker → Forex → default_warmup_trading_days`, 1–60). A day counts when at least `min_closed_bars_per_day` (default 1) realtime bars close while forex is open.

Promote: `POST /api/strategies/{id}/promote` (or Strategies UI). Only allowed from `ready` (or already `live`). Disabling and re-enabling starts a **new warm-up episode** — never jumps straight to live.

### Catchup hard gates

When the pipeline context is catchup/bootstrap:

- No LLM calls for AI Strategy decisions
- Warm-up progress does not advance
- No Associate dispatch for non-live AI strategies

## Params (`params.ai`)

Knobs under `params.ai` (validated in `strategies/params/ai_section.py`):

| Field | Default | Notes |
|-------|---------|-------|
| `model_id` | `null` | Bound LLM from Settings → Models |
| `use_daily_report` / `use_weekly_brief` / `use_weekly_debrief` | `true` | Research bias toggles |
| `llm_mode` | `off` | `off` \| `on_signal_change` \| `interval` \| `manual` |
| `min_llm_interval_minutes` | `240` | Throttle between decisions (15–10080) |
| `max_llm_calls_per_day` | `12` | Strategy-level cap |
| `max_llm_calls_per_symbol_per_day` | `4` | Per-symbol cap |
| `max_context_bars` | `64` | Bars sent as context (16–500) |
| `learn_enabled` | `false` | Outcome → memory digest learning |

Signal block: `signal.type = "ai_strategy"` (runtime: `ModelSignalRuntime`). Sync `evaluate()` is always fail-closed (no LLM); live analysis uses `evaluate_async()`.

Shared sections (`timeframe`, `exits`, `risk`, `execution`, `min_candles`) work like other presets. See [params-schema](./params-schema.md).

## Shadow trading

Warming/ready intents never write `broker_lots`. Isolated tables:

| Table | Purpose |
|-------|---------|
| `shadow_intents` | Would-have entry intents |
| `shadow_lots` | Simulated open/closed shadow positions |
| `trade_outcome_records` | Normalized outcomes (shadow or live) for learning |

Broker forks AI Strategy intents before Associate: shadow path records; live path uses normal execution. Priority resolution prefers **live** strategies over warming AI when both signal the same pair.

## Spend safety

LLM calls go through `brokerai.cost.llm_guard` (reserve before HTTP, settle after):

| Control | Where |
|---------|--------|
| Env kill switch | `BROKERAI_LLM_KILL_SWITCH=true` |
| Settings kill switch + daily USD limit | `llm_budget_settings` / API |
| Per-day spend ledger | `llm_budget_days` |
| In-flight reservations | `llm_call_reservations` |
| Strategy throttles | `params.ai` interval / max calls |

No per-candle LLM by default (`llm_mode=off`). Catchup never spends. Research reports remain separate scheduled jobs.

## Learning

When outcomes close (shadow or live) and learning is enabled:

1. Outcomes land in `trade_outcome_records`
2. `learning_jobs` queue digests work
3. Digests persist in `strategy_memory_digests`
4. Digests feed the next decision prompt and daily playbook compile

Research guidance snapshots live in `strategy_guidance` (bias only — not executable rules).

## Daily improve (compiled backtests)

Secretary can queue **at most one** daily AI Strategy backtest per strategy (ET calendar day) when enabled in backtest settings:

| Setting | Purpose |
|---------|---------|
| `daily_ai_strategy_backtest_enabled` | Master switch |
| `daily_ai_strategy_backtest_period` | Lookback period (e.g. `6m`) |

Flow:

1. Compile latest digest → ephemeral strategy with `signal.type=compiled_playbook`
2. Run via the backtesting engine (no live LLM in the bar loop)
3. Optional Auto AI feedback → merge notes into memory digest
4. UI **Apply in builder** is blocked for runs with `origin=ai_strategy_daily`

Manual / general backtests use `/research/backtest` and `/api/backtest-runs`.

## UI

| Surface | Behavior |
|---------|----------|
| Strategies → New → **AI Strategy** | Builder for `params.ai` + shared risk/execution |
| Strategies list | Phase badge, warm-up progress, **Promote** when ready |
| Backtesting | Manual runs + toggles for daily AI Strategy improve |
| Analysis / Activity | Standard analyzer runs and pipeline events |

## Module layout

```
src/brokerai/ai_strategy/          — lifecycle, shadow, learning, compile, daily BT
src/brokerai/strategies/presets/ai_strategy/
src/brokerai/trading/presets/ai_strategy/   — ModelSignalRuntime
src/brokerai/backtesting/          — engine, coordinator, AI feedback
src/brokerai/cost/llm_guard.py     — spend gate
frontend/.../presets/aiStrategy/   — builder
```

## API (AI-related)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/strategies/{id}/promote` | Promote ready AI Strategy to live |
| GET/PUT | `/api/backtest/settings` | Includes daily AI Strategy BT toggles |
| GET/POST | `/api/backtest-runs` | List / create backtest runs |
| POST | `/api/backtest-runs/{id}/ai-feedback` | Auto AI feedback on a completed run |
| GET/PUT | `/api/settings/llm-budget` (or equivalent budget route) | Kill switch + daily USD limit |

## Tests

```bash
./venv/bin/python -m pytest tests/test_ai_strategy_slice1.py tests/test_ai_strategy_slice2.py \
  tests/test_ai_strategy_slice3.py tests/test_ai_strategy_slice4.py
```

## Known limits

- Forex only; no multi-asset AI Strategy
- No auto-promote; warm-up must finish and user must promote
- Shadow ledger ≠ OANDA paper / `broker_lots`
- Daily backtests use compiled playbook, not the live LLM runtime
- Walk-forward and BT regression gates are not implemented
