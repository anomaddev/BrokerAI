# Orchestrator and bot loops

BrokerAI runs as a single Python asyncio process: the **orchestrator** loads enabled sub-bots, schedules their work on configurable intervals, and runs auxiliary loops for heartbeat, control IPC, and activity monitoring.

Trading is coordinated by the **Secretary** pipeline. See [The Loop](./the-loop.md) for `secretary` → workers → `broker` architecture.

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
4. Auto-injects `secretary` and `broker` when missing from `enabled_bots`.
5. Registers SIGTERM/SIGINT handlers.
6. Calls `start_all()` to start bots and spawn tick tasks.
7. Ensures Postgres schema (`ensure_indexes()` → `ensure_schema()` / SQLAlchemy `create_all`).
8. Spawns heartbeat, control, and activity-monitor loops.
9. Waits for shutdown signal, then cancels auxiliary tasks and `stop_all()`.

## Enabled bots

Bots are registered in `src/brokerai/bots/__init__.py`:

| Name | Class | Role |
|------|-------|------|
| `secretary` | `SecretaryBot` | Candle timeline, pipeline dispatch, timed research |
| `broker` | `BrokerBot` | Execution gates, exit monitors, associate dispatch, OANDA sync |
| `researcher` | `ResearcherBot` | Research scheduling hook (workers run on Secretary dispatch) |

`secretary` and `broker` are always loaded even if omitted from `BROKERAI_ENABLED_BOTS`. Default: `secretary,broker,researcher`.

## Bot contract

All bots inherit from `Bot` (`src/brokerai/bots/base.py`):

- **`start()`** — sets state to `RUNNING`, calls `on_start()`.
- **`tick()`** — one iteration of periodic work (abstract; each bot implements it).
- **`stop()`** — calls `on_stop()`, sets state to `STOPPED`.

The orchestrator does not embed business logic; it only calls `tick()` on a timer.

## Orchestrator lifecycle

### Loading and wiring

On init, `_load_bots()`:

1. Resolves bot names (auto-injecting `secretary` + `broker`).
2. Instantiates each registered bot.
3. Wires `secretary.attach_broker(broker)` and `broker.attach_data_manager(secretary.service)`.

### Startup sequence (`start_all`)

1. **`bot.start()`** for every enabled bot.
2. **Startup pass** — `secretary.run_startup_pass()` warms candle cache and runs initial analysis when due.
3. **Spawn tick tasks** — one `asyncio.create_task(_run_bot(...))` per bot with per-bot intervals.
4. Record orchestrator-started activity.

### Per-bot tick loop (`_run_bot`)

Tick intervals (`_tick_interval_seconds`):

| Bot | Default interval | Setting |
|-----|------------------|---------|
| `secretary` | 5s | `BROKERAI_SECRETARY_TICK_INTERVAL_SECONDS` |
| `broker` | 30s | `BROKERAI_BROKER_SYNC_INTERVAL_SECONDS` |
| `researcher` | 5s | (fixed) |

```python
while self._running:
    try:
        await bot.tick()
        await asyncio.sleep(interval)
    except asyncio.CancelledError:
        break
    except Exception as exc:
        # log, mark bot ERROR, record activity
        await asyncio.sleep(interval)
```

Bots run in **parallel** (separate asyncio tasks). Errors are logged and recorded; the loop continues unless the orchestrator is shutting down.

### Auxiliary loops

| Loop | Interval | Purpose |
|------|----------|---------|
| `heartbeat_loop` | 10s | Writes `heartbeat.json` under the data dir |
| `control_loop` | 0.5s | Processes pending start/stop commands from CLI/web |
| `activity_monitor_loop` | 60s | Activity monitor housekeeping |

### Shutdown

SIGTERM or SIGINT sets a stop event. The orchestrator cancels auxiliary tasks, then `stop_all()`:

- Cancels all bot tick tasks.
- Calls `bot.stop()` on each bot.
- Clears running state.

## Secretary tick (summary)

On each secretary tick:

1. Build work units for due `(symbol, timeframe)` candle closes.
2. Dispatch ephemeral workers (data manager, data analyst) via the worker pool.
3. Forward analysis results to `broker.process_analysis()`.
4. Run scheduled research when due.

Full breakdown: [The Loop](./the-loop.md), [Data Manager](./data-manager.md).

## Broker tick (summary)

On each broker tick:

1. Housekeeping for exit monitors and sub-analyzers.
2. `run_broker_sync()` when the sync interval elapses.
3. Consume execution intents from Secretary analysis when attached.

## Observability

| Mechanism | Location / command |
|-----------|-------------------|
| Heartbeat file | `{data_dir}/heartbeat.json` |
| CLI status | `brokerai bots list --json` |
| Pipeline status | `GET /api/pipeline/status` |
| Activity log | Bot errors and orchestrator start/stop |

## Related docs

- [The Loop](./the-loop.md) — Secretary-coordinated pipeline
- [Data Manager](./data-manager.md) — candle fetch service and workers
- [Caching strategy](./caching.md) — Postgres vs in-process cache
- [Strategy params schema](../strategies/params-schema.md)
