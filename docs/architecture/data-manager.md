# Data Manager

The **Data Manager** is BrokerAI’s forex OHLCV cache layer: an **ephemeral worker** plus a long-lived **`DataManagerService`** owned by the Secretary. It pulls closed bars from OANDA and upserts them into Postgres (`brokerai.market_candles`). Other components read candles through `DataManagerService` rather than calling OANDA directly.

It is **not** a persistent bot. Scheduling and pipeline dispatch live on the Secretary; the worker runs per `CandleJob` / pipeline request.

See also: [The Loop](./the-loop.md), [Orchestrator and bot loops](./orchestrator-and-bot-loops.md), [Caching strategy](./caching.md).

## Role in the system

```
Enabled strategies ──┐
Explore chart watches ──┼──► Secretary (timeline / pipeline)
On-demand consumers ──┘              │
                                     ▼
                         DataManagerWorker (per job)
                                     │
                                     ▼
                     DataManagerService → CandleCache
                                     │
                                     ▼
                        Postgres brokerai.market_candles
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
      Data Analyst worker        Broker / exits        Web Explore UI
```

| Responsibility | Owner |
|----------------|-------|
| When to fetch (candle closes) | Secretary candle timeline + pipeline |
| How to fetch / upsert | `CandleCache` + `fetch_and_cache_forex_candles` |
| Public read API | `DataManagerService` |
| Strategy-driven demand | `collect_candle_requirements` / forex strategy loaders |
| UI-driven demand | `candle_watch` table + `collect_watch_requirements` |

## Module layout

Under `src/brokerai/bots/data_manager/`:

| File | Purpose |
|------|---------|
| `worker.py` | `DataManagerWorker` — ephemeral fetch for a `PipelineContext` |
| `service.py` | `DataManagerService` — gateway for consumers; demand tracking |
| `candles.py` | Bootstrap detection, batched OANDA sync via `fetch_and_cache_forex_candles` |
| `candle_requirements.py` | `CandleRequirement` dataclass; merge strategy needs by timeframe |
| `candle_schedule.py` | Next candle close time; fetch-due helpers |
| `candle_watch.py` | Load active Explore watches from Postgres |
| `forex_strategies.py` | Which enabled strategies need forex candles |

Persistence and OANDA HTTP live in `src/brokerai/trading/data/candle_cache.py` and `src/brokerai/db/repositories/market_data.py`.

## Lifecycle

### Service registration (Secretary)

On Secretary `on_start`:

1. Instantiates `DataManagerService` and registers it process-wide (`set_data_manager_service`).
2. Orchestrator wires `broker.attach_data_manager(secretary.service)`.
3. Web and workers resolve candles via `get_data_manager_service()` / `require_data_manager_service()`.

On Secretary `on_stop`, the global pointer is cleared. Without the orchestrator, `require_data_manager_service()` / `DataManagerService.create_standalone()` still serve web/dev reads, but **scheduled candle pipelines** only run when Secretary is active.

### Worker (`DataManagerWorker.run`)

For each pipeline request:

1. Build a `CandleRequirement` from `(symbol, timeframe, bar_count)`.
2. Call `fetch_and_cache_forex_candles` (respects `BROKERAI_OANDA_FETCH_CONCURRENCY`).
3. Set `latest_candle_time` and `fetch_status` on the `PipelineContext`.
4. Return upsert counts / errors in worker metadata.

CLI helpers (`brokerai candles sync|backfill|verify|repair|status`) use the same cache/service paths outside the live pipeline.

## Demand sources

1. **Enabled strategies** — `load_runnable_forex_strategies()` loads enabled strategies from Postgres, requires forex enabled in Settings → Broker with overlapping pairs.
2. **Explore watches** — rows in `brokerai.candle_watch`.
3. **Registered demand** — consumers calling `request_candles` / `ensure_coverage` record symbol/timeframe/bar_count for coverage planning.

## Service API (consumers)

| Method | Behavior |
|--------|----------|
| `request_candles(...)` | Record demand → `ensure_coverage` → read from Postgres |
| `ensure_coverage(...)` | Bootstrap or incremental fetch until bar count is satisfied |
| `latest_candle_time(...)` | Latest closed bar time for revision / pipeline gating |
| `registered_demand()` | Current in-process demand map |

## Postgres tables

| Table | Role |
|-------|------|
| `brokerai.market_candles` | Cached OHLCV (`UNIQUE` symbol/timeframe/source/ts) |
| `brokerai.candle_sync_state` | Per-series fetch scheduling state |
| `brokerai.candle_watch` | Explore (and similar) close watches |

Schema is ensured on API/orchestrator startup via `ensure_indexes()` → `ensure_schema()`.

## Configuration

| Setting | Purpose |
|---------|---------|
| `BROKERAI_ENABLED_BOTS` | Must include `secretary` (owns the service and schedules workers) |
| `BROKERAI_PIPELINE_CONCURRENCY` | Max parallel Secretary pipelines |
| `BROKERAI_OANDA_FETCH_CONCURRENCY` | Nested cap for OANDA candle fetches |
| `BROKERAI_DATABASE_URL` | Postgres (Supabase) |

## Related docs

- [The Loop](./the-loop.md) — Secretary → workers → Broker
- [Data Analyzer](./data-analyzer.md) — strategy analysis worker
- [Caching strategy](./caching.md) — Postgres vs in-process cache
