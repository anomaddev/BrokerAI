# Data Analyzer

The **Forex Data Analyst** is an **ephemeral worker** under the Secretary pipeline. On each due candle close it loads cached OHLCV bars, evaluates enabled strategies for that `(symbol, timeframe)`, and persists each run to Postgres (`brokerai.strategy_analysis_runs`). Results are returned to the Secretary, which forwards them to Broker for gates, exit monitors, and Associate dispatch.

It is **not** a persistent bot. There is no analyzer tick loop and no Executor handoff.

See also: [The Loop](./the-loop.md), [Data Manager](./data-manager.md), [Strategy params schema](../strategies/params-schema.md).

## Role in the system

```
Secretary pipeline (CandleJob / PipelineContext)
        │
        ▼
DataManagerWorker ──► Postgres market_candles
        │
        ▼
ForexDataAnalystWorker
        │
        ├── run_strategy_analysis (in-process)
        ├── StrategyAnalysisRunsRepository.insert_from_result
        └── WorkerResult[list[AnalysisResult]]
        │
        ▼
Broker.process_analysis() ──► gates / exits / Associates
```

| Responsibility | Owner |
|----------------|-------|
| When to analyze | Secretary candle timeline + pipeline |
| Load bars | `fetch_live_candles_for_unit` via `DataManagerService` |
| Evaluate signals | `run_strategy_analysis` + indicator cache |
| Persist runs | `StrategyAnalysisRunsRepository` |
| Act on results | Broker (not this worker) |

## Module layout

Under `src/brokerai/bots/data_analyzer/`:

| File | Purpose |
|------|---------|
| `worker.py` | `ForexDataAnalystWorker` — per-pipeline strategy analysis |
| `assets/` | Asset-class stubs / registration hooks |

Shared trading logic lives in `src/brokerai/trading/pipeline.py`, `indicator_cache.py`, `candle_context.py`, and strategy evaluators under `src/brokerai/strategies/`.

## Worker (`ForexDataAnalystWorker.run`)

1. If `PipelineContext.strategies` is empty, return success with no results.
2. Build a `WorkUnit` from the pipeline context.
3. Load candles via `fetch_live_candles_for_unit` (uses the process-global `DataManagerService`).
4. Warm `IndicatorCache` for the strategy params on those bars.
5. For each strategy: `run_strategy_analysis(...)`, persist with `insert_from_result`, attach `run_id`, log the result.
6. Return `WorkerResult` with the list of `AnalysisResult` and metadata (`latest_candle_time`, `count`).

Exit monitoring for open lots is owned by the **Broker** bot (exit monitors / sub-analyzers on the broker side), not this worker.

## Persistence

Each analysis run is written to Postgres table `brokerai.strategy_analysis_runs` (JSONB doc + indexed candle/strategy fields). Runs are keyed for idempotent upserts per `(strategy, pair, candle_time)` so re-analysis updates in place rather than appending unbounded history.

The Analysis UI (`/research/analysis`) reads this table via `/api/strategy-analysis-runs`.

## Dependencies

| Requirement | Notes |
|-------------|-------|
| Secretary + Broker enabled | Pipeline dispatch and execution authority |
| `DataManagerService` registered | Secretary `on_start` (or standalone for web-only) |
| Candles in `market_candles` | Data Manager worker / `ensure_coverage` |
| Enabled strategies in Postgres | `brokerai.strategies` |

## Configuration

| Setting | Purpose |
|---------|---------|
| `BROKERAI_ENABLED_BOTS` | `secretary,broker,researcher` (default) |
| `BROKERAI_PIPELINE_CONCURRENCY` | Max parallel pipelines (analysis shares this pool) |

## Related docs

- [The Loop](./the-loop.md)
- [Data Manager](./data-manager.md)
- [Orchestrator and bot loops](./orchestrator-and-bot-loops.md)
- [OANDA entity linkages](./oanda-entity-linkages.md) — ledger after Broker acts
