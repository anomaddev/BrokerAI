# Orchestrator and bot loops

BrokerAI runs as a single Python asyncio process: the **orchestrator** loads enabled sub-bots, schedules their work on a fixed interval, and runs auxiliary loops for heartbeat, control IPC, and activity monitoring.

This document describes how that main loop works and how the trading pipeline (`data_manager` → `data_analyzer` → `executor` → `brokers`) fits together.

## Entry point

The orchestrator process starts via:

```bash
python -m brokerai.orchestrator
# or: brokerai run orchestrator
```

`run_orchestrator()` in `src/brokerai/core/orchestrator.py`:

1. Configures logging and validates startup settings.
2. Reconciles stale background tasks (research jobs, etc.).
3. Builds the orchestrator singleton and loads enabled bots from config.
4. Registers SIGTERM/SIGINT handlers.
5. Calls `start_all()` to start bots and spawn tick tasks.
6. Ensures MongoDB indexes.
7. Spawns heartbeat, control, and activity-monitor loops.
8. Waits for shutdown signal, then cancels auxiliary tasks and `stop_all()`.

## Enabled bots

Bots are registered in `src/brokerai/bots/__init__.py`:

| Name | Class | Role |
|------|-------|------|
| `researcher` | `ResearcherBot` | Scheduled daily/weekly research reports |
| `data_manager` | `DataManagerBot` | Fetch and cache OHLCV from OANDA into MongoDB |
| `data_analyzer` | `DataAnalyzerBot` | Run strategy analysis on new candles; monitor open-trade exits |
| `executor` | `ExecutorBot` | Apply execution gates and queue trade intents |
| `brokers` | `BrokersBot` | Route trade intents to asset-class sub-brokers |

Which bots actually run is controlled by the `enabled_bots` setting (comma-separated list). Default in settings is `"researcher"` only; trading bots must be enabled explicitly, e.g. `data_manager,data_analyzer,executor,brokers`.

## Bot contract

All bots inherit from `Bot` (`src/brokerai/bots/base.py`):

- **`start()`** — sets state to `RUNNING`, calls `on_start()`.
- **`tick()`** — one iteration of periodic work (abstract; each bot implements it).
- **`stop()`** — calls `on_stop()`, sets state to `STOPPED`.

The orchestrator does not embed business logic; it only calls `tick()` on a timer. Each bot decides whether to do real work on a given tick.

## Orchestrator lifecycle

### Loading and wiring

On init, `_load_bots()`:

1. Instantiates each bot listed in `enabled_bot_names`.
2. Wires shared dependencies:
   - `DataManagerService` from `data_manager` → attached to `data_analyzer`, `executor`, and `brokers`.
   - `data_analyzer` → attached to `executor`.
   - `executor` → attached to `brokers`.

### Startup sequence (`start_all`)

1. **`bot.start()`** for every enabled bot.
2. **Startup pass** (`_run_startup_pass`) — runs once before periodic loops:
   - `data_manager.tick()` — warm candle cache (bootstrap/incremental fetch if due).
   - `data_analyzer.run_startup_pass()` — calls `tick()` once for initial analysis.
   - `executor.run_startup_pass()` — calls `tick()` once to process initial analysis results.
3. **Spawn tick tasks** — one `asyncio.create_task(_run_bot(...))` per bot.
4. Record orchestrator-started activity.

The startup pass avoids waiting for the first 5-second cycle to populate cache and run analysis.

### Per-bot tick loop (`_run_bot`)

```python
while self._running:
    try:
        await bot.tick()
        await asyncio.sleep(5)
    except asyncio.CancelledError:
        break
    except Exception as exc:
        # log, mark bot ERROR, record activity
        await asyncio.sleep(5)
```

Every enabled bot gets `tick()` roughly every **5 seconds**, in **parallel** (separate asyncio tasks). Errors are logged and recorded; the loop continues unless the orchestrator is shutting down.

### Auxiliary loops

These run alongside bot tick tasks in the same process:

| Loop | Interval | Purpose |
|------|----------|---------|
| `heartbeat_loop` | 10s | Writes `heartbeat.json` under the data dir (timestamp, running flag, per-bot status) |
| `control_loop` | 0.5s | Processes pending start/stop commands from CLI/web via control IPC |
| `activity_monitor_loop` | 60s | Activity monitor housekeeping |

### Shutdown

SIGTERM or SIGINT sets a stop event. The orchestrator cancels auxiliary tasks, then `stop_all()`:

- Cancels all bot tick tasks.
- Calls `bot.stop()` on each bot.
- Clears running state.

## Local development: single-bot loop

For development without the full orchestrator:

```bash
brokerai run data-manager          # tick every 5s until interrupted
brokerai run data-manager --once   # single tick
```

Implementation: `src/brokerai/bots/dev_loop.py` (`run_bot_loop`) — same pattern: `start()` → repeated `tick()` → `stop()` on signal.

## Trading pipeline

When all trading bots are enabled, one logical cycle looks like this:

```
data_manager.tick  →  MongoDB (market_data)
       ↓
data_analyzer.tick  →  in-memory AnalysisResult (+ strategy_analysis_runs)
       ↓
executor.tick  →  in-memory TradeIntent queue
       ↓
brokers.tick  →  asset-class sub-brokers (place_order)
```

Bots run in parallel on the same 5s schedule. Ordering within a single window is not strictly guaranteed; the design uses revision tracking, processed-at deduplication, and an intent queue to stay consistent.

### 1. Data manager (`data_manager.tick`)

**File:** `src/brokerai/bots/data_manager/bot.py`

On each tick:

1. Load runnable forex strategies and chart **watch requirements** (Explore candle watches).
2. Build candle requirements (pairs, timeframes, bar counts) via `collect_candle_requirements`.
3. Plan fetches:
   - **Bootstrap** — MongoDB has fewer bars than required; pull history from OANDA once.
   - **Incremental** — next scheduled candle close is due; fetch newly closed bar(s).
   - **Waiting** — nothing due yet; skip OANDA for that timeframe.
4. Call `fetch_and_cache_forex_candles` when bootstrap or incremental work exists.
5. Upsert into `market_data` and schedule `_next_fetch_at` per timeframe.

**Important:** The orchestrator ticks every ~5 seconds, but OANDA is **not** called every tick — only on bootstrap or when a scheduled candle close is due.

Full breakdown: [Data Manager](./data-manager.md). See also [caching.md](./caching.md) and README section on forex candle cache.

Status includes `next_candle_fetches` per timeframe (`brokerai bots list --json`).

### 2. Data analyzer (`data_analyzer.tick`)

**File:** `src/brokerai/bots/data_analyzer/bot.py`

On each tick:

1. Require attached `DataManagerService`; load forex asset runtime and runnable strategies.
2. Build a **work plan** — units of `(pair, timeframe, strategies)`.
3. For each unit, read latest candle time from the data manager and compare to `GLOBAL_CANDLE_REVISIONS`:
   - **Skip** if no new closed bar since last analysis.
4. **`_sync_exit_monitors`** — maintain `_TradeExitAnalyzer` sub-analyzers for open trades; evaluate exit conditions when pairs were just analyzed.
5. For units with new candles:
   - Load bars via `load_candles_for_unit`.
   - Warm `IndicatorCache` for strategy params.
   - Run `run_strategy_analysis` per strategy; persist via `StrategyAnalysisRunsRepository`.
   - Store results in `_last_results`; mark candle revision updated.

Analysis is **revision-gated** — most ticks are no-ops when no new bars exist.

Full breakdown: [Data Analyzer](./data-analyzer.md).

Startup: `run_startup_pass()` calls `tick()` once so cached candles are analyzed immediately after the data manager warm-up.

### 3. Executor (`executor.tick`)

**File:** `src/brokerai/bots/executor/bot.py`

On each tick:

1. Read `data_analyzer.get_recent_results()`.
2. Filter to **unprocessed** results using `_processed_analysis_at` keyed by `(strategy_id, pair)` and `analyzed_at`.
3. Refresh strategy definitions; load daily trade counts and forex session settings.
4. For each new result, run **`passes_execution_gates`** (limits, sessions, etc.). Persist gated-out outcomes on the analysis run.
5. **`resolve_priority_conflicts`** among strategies competing on the same pair.
6. For winners, load candles and optionally **`maybe_confirm_trade_intent`** (AI confirmation).
7. Set **`_pending_intents`**; mark results processed; persist execution metadata on analysis runs.

Startup: `run_startup_pass()` calls `tick()` once after the analyzer startup pass.

### 4. Brokers (`brokers.tick`)

**File:** `src/brokerai/bots/brokers/bot.py`

On each tick:

1. **`consume_pending_intents()`** from the executor (clears the queue).
2. For each intent, **`route(asset_class, "place_order", payload)`** to the matching sub-broker (forex, crypto, stocks, futures, options, metals).

The executor produces intents; the brokers bot consumes and routes — decoupled by an in-memory queue, typically on the same or next 5s tick.

## Researcher bot

**File:** `src/brokerai/bots/researcher/bot.py`

On each tick (when scheduled reports are enabled and no research task is already running):

1. Check whether a **daily report** is due (market schedule + not already run today).
2. Else check **weekly brief** schedule.
3. Else check **weekly debrief** schedule.

When due, starts the corresponding background task via `start_scheduled_*_task()` helpers. Does not block the tick loop for long-running LLM work.

## Example timeline (all trading bots enabled)

Assume a new M15 bar closes shortly after startup:

| Time | What happens |
|------|----------------|
| T+0 | Startup pass: data_manager fetches/updates M15 bars; analyzer runs once; executor processes results; brokers may route intents |
| T+0–5s | Parallel ticks: data_manager may incremental-fetch; analyzer sees revision change and analyzes; executor queues intents; brokers consumes |
| T+5–15m | Most ticks no-op until next M15 close (data_manager schedules fetch; analyzer skips until revision changes) |

## Observability

| Mechanism | Location / command |
|-----------|-------------------|
| Heartbeat file | `{data_dir}/heartbeat.json` — running flag, bot states, timestamps |
| CLI status | `brokerai bots list --json` — includes `next_candle_fetches`, registered candle demand |
| Activity log | Bot errors and orchestrator start/stop recorded via activity system |
| Dev single tick | `brokerai run <bot> --once` |

## Related docs

- [Data Manager](./data-manager.md) — candle requirements, scheduling, OANDA sync, and service API
- [Data Analyzer](./data-analyzer.md) — work plan, revision gating, analysis pipeline, exit monitors
- [Caching strategy](./caching.md) — MongoDB vs Redis, task coordination
- [Strategy params schema](../strategies/params-schema.md) — params read by data manager and analyzer
- README — forex candle cache requirements and `enabled_bots` configuration
