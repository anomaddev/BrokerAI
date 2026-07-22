# The Loop — Secretary-Coordinated Architecture

BrokerAI's trading pipeline is coordinated by the **Secretary** bot: a persistent task scheduler that runs spin-up/spin-down workers for data fetch, analysis, and execution.

See also: [Orchestrator and bot loops](./orchestrator-and-bot-loops.md), [Data Manager](./data-manager.md), [Data Analyzer](./data-analyzer.md).

## Persistent vs ephemeral bots

| Persistent | Role |
|------------|------|
| **Orchestrator** | Process lifecycle, heartbeat, control IPC |
| **Secretary** | Candle timeline, pipeline dispatch, timed research, activity log |
| **Broker** | Execution gates, exit monitors, associate dispatch |
| **Researcher** | Host for research scheduling (workers run on Secretary dispatch) |

| Ephemeral (spin-up/spin-down) | Role |
|-------------------------------|------|
| **Data Manager worker** | Fetch/cache candles per request |
| **Data Analyst worker** | Run strategy analysis per WorkUnit |
| **Associate worker** | Place orders per asset class |
| **Researcher worker** | Daily/weekly reports on demand |

## M15 pipeline flow

For each due `(symbol, timeframe)` WorkUnit at candle close:

1. Secretary creates `CandleJob` + `PipelineContext`
2. Data Manager worker upserts candles to Postgres (`brokerai.market_candles`)
3. Data Analyst worker loads bars via `DataManagerService` (optional hot cache)
4. Broker `process_analysis()` applies gates, exit monitors, dispatches Associates

Parallelism is controlled by `BROKERAI_PIPELINE_CONCURRENCY` (default 10) with nested caps for OANDA fetches and analysis CPU.

### AI Strategy fork

When an enabled strategy has `preset_id=ai_strategy`:

- **Warming / ready** — Broker records would-have intents in `shadow_intents` / `shadow_lots` (never `broker_lots`). Warm-up advances only on realtime bars (catchup never advances or calls the LLM).
- **Live** — Normal Associate dispatch after gates; priority prefers live strategies over warming AI on the same pair.
- **Daily improve** — Secretary may queue at-most-daily compiled-playbook backtests when backtest settings enable them.

Details: [AI Strategy](../strategies/ai-strategy.md).

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `BROKERAI_ENABLED_BOTS` | `secretary,broker,researcher` | Persistent bots |
| `BROKERAI_PIPELINE_CONCURRENCY` | `10` | Max parallel pipelines |
| `BROKERAI_SECRETARY_TICK_INTERVAL_SECONDS` | `5` | Secretary tick |
| `BROKERAI_BROKER_SYNC_INTERVAL_SECONDS` | `30` | Broker slow tick |

**Recommended production:**

```bash
BROKERAI_ENABLED_BOTS=secretary,broker,researcher
```

## Migration status

- Forex end-to-end via Secretary: **implemented**
- Multi-asset (stocks, options, futures, metals, crypto): **stubs only** (`TODO(loop)`)
- Account snapshots: **persisted** via `OandaAccountSnapshotsRepository` / OANDA sync; Broker exit monitors also keep an in-memory hot cache
- Researcher trade-analysis mode: **not implemented** (`TODO(loop)`)

## Observability

- Heartbeat: `{data_dir}/heartbeat.json` includes `pipeline` section
- API: `GET /api/pipeline/status`
- Activity log: `pipeline_*` action types with `job_id` correlation

## Module layout

```
src/brokerai/bots/secretary/     — coordinator (+ daily AI Strategy backtest tick)
src/brokerai/bots/broker/        — execution authority (+ shadow fork)
src/brokerai/bots/associate/     — per-asset order workers
src/brokerai/bots/data_manager/worker.py
src/brokerai/bots/data_analyzer/worker.py
src/brokerai/ai_strategy/        — lifecycle, shadow, learning, compile, daily BT
src/brokerai/backtesting/        — backtest engine + AI feedback
src/brokerai/cost/llm_guard.py   — LLM spend gate
src/brokerai/core/worker_pool.py
src/brokerai/core/pipeline_candle_cache.py
```
