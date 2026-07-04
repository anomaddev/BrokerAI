# OANDA Entity Linkages: Trades, Positions, Orders & Transactions

**BrokerAI Architecture Document**  
**Audience:** Senior engineers performing API structure review for efficiencies  
**Last updated:** 2026-07-04

This document provides an extreme-detail mapping of how OANDA's native trading entities (Trades, Positions, Orders, Transactions) are normalized, linked, and persisted inside BrokerAI. It is intended for architecture reviews, reconciliation audits, and future multi-broker abstraction work.

See also:
- [Data Manager architecture](./data-manager.md)
- [Orchestrator & bot loops](./orchestrator-and-bot-loops.md)
- `.response_data/oanda/trades/README.md` (sample payloads)

---

## 1. Core Domain Models (`src/brokerai/trading/broker/models.py`)

BrokerAI never stores raw OANDA objects directly as primary records. All broker data is normalized into three immutable/value-oriented dataclasses:

### `PositionLot` (lines 62–107)
The **atomic unit of exposure**. Every OANDA trade (open or closed) becomes exactly one `PositionLot`.

Key linkage fields:
- `broker_lot_id: str` — OANDA `trade.id` / `tradeID` (primary key within an account)
- `stop_loss: ChildOrder | None`, `take_profit: ChildOrder | None` — embedded child orders
- `closing_event_ids: list[str]` — transaction IDs that reduced/closed the lot
- `entry_batch_id: str | None`, `last_event_id: str | None`
- `raw_broker: dict | None` — full original OANDA trade payload for audit/debug

Other fields (`initial_qty`, `current_qty`, `entry_price`, `unrealized_pl`, `realized_pl`, `costs`, strategy metadata, etc.) are derived or enriched later.

### `ChildOrder` (lines 12–58)
Normalized representation of attached bracket orders (STOP_LOSS, TAKE_PROFIT, etc.).

Linkage fields:
- `broker_order_id`
- `trade_id` — back-reference to parent `PositionLot.broker_lot_id`
- `filling_event_id`, `cancelling_event_id` — transaction IDs

### `BrokerEvent` (lines 174–209)
**Immutable audit record** of a single OANDA transaction.

Linkage fields:
- `broker_event_id` = transaction `id`
- `broker_lot_id` = `tradeID` (may be populated from `tradeClosed` / `tradesClosed` objects)
- `broker_order_id` = `orderID` (or from `orderFillTransaction`)
- `batch_id` — groups atomic multi-transaction operations (e.g., MARKET_ORDER + TRADE_OPENED + MARGIN_USED)
- `request_id` — client-provided correlation ID

`BrokerEvent` is the only place where cross-entity relationships (trade ↔ order ↔ transaction) are explicitly denormalized for efficient queries.

### `InstrumentExposure` (lines 213+)
Computed rollup (not persisted from OANDA). Aggregates open `PositionLot`s by `(instrument, direction)`.

---

## 2. OANDA API Layer & Normalization (`src/brokerai/integrations/oanda.py`)

All raw HTTP responses are processed through pure normalization functions before any domain model is created.

### Key Normalizers

| Function | Input | Output | Linkage Extraction |
|----------|-------|--------|--------------------|
| `_normalize_oanda_open_trade` (158–206) | Trade object from `/openTrades` or Account Details | Normalized dict | Embeds `stopLossOrder` / `takeProfitOrder` via `_normalize_oanda_child_order` (209–226) which captures `tradeID`, `fillingTransactionID`, `cancellingTransactionID` |
| `_normalize_oanda_trade_raw` (229+) | Any trade (open/closed) | Normalized dict | Handles `state`, `initialUnits`/`currentUnits`, `closingTransactionIDs` |
| `normalize_oanda_transaction` (276–320) | Single transaction payload | Normalized dict | Resolves `trade_id` from `tradeID` or nested `tradeClosed`/`tradesClosed`; resolves `order_id` from `orderID` or `orderFillTransaction`; always captures `batchID`, `requestID` |
| `normalize_account_summary_fields` (44–59) | Account summary | Flat summary | `lastTransactionID` surface |

### Fetch Endpoints Used

- `GET /accounts/{id}` (`get_account_details`, 74–87) — **Primary bootstrap source**. Returns `account` containing:
  - `trades[]` (open only)
  - `orders[]` (pending)
  - `positions[]`
  - `lastTransactionID`
- `GET /pendingOrders` (`list_pending_orders`, 632–640)
- `GET /positions` (`list_positions`, 643–653) — **Periodic health check only** (`validate_exposure`, gated by `oanda_exposure_check_interval_seconds`)
- `GET /changes?sinceTransactionID=...` (`poll_account_changes`, 90–112) — Incremental delta (changes + state)
- Transaction range queries (`list_transactions_since`, `list_transactions_idrange`, 552+)
- `GET /trades?state=...` and `/trades/{tradeID}` for closed-trade history (Account Details never includes closed trades)

`list_all_trades` + `get_broker_trade` handle the open/closed split.

---

## 3. Adapter & State Application Layer

### `src/brokerai/trading/broker/adapters/oanda.py`

- `lot_from_oanda_trade` (63–100+) — Normalized trade dict → `PositionLot` + `ChildOrder`s
- `event_from_oanda_transaction` (119–141) — Normalized txn → `BrokerEvent` (populates both `broker_lot_id` and `broker_order_id`)
- `OandaAdapter.sync_lots` (152–217) — Orchestrates full bootstrap (`get_account_details` + closed backfill) vs incremental (cursor-driven)
- `validate_exposure` (343–389) — Fetches OANDA Positions, aggregates by `(instrument, long/short)`, compares against sum of open `PositionLot.current_qty`

### `src/brokerai/trading/oanda_account_state.py`

- `lots_from_account_details` (76–99) — Iterates `account["trades"]`
- `_normalize_trade_summary` (54–73) — Handles TradeSummary shape from `/changes`
- `apply_account_changes` / `open_lots_from_account_state` — Incremental lot + event application
- `detect_transaction_gap` — Cursor gap detection for repair triggers

### Persistence (`BrokerLotsRepository`, `BrokerEventsRepository`)

- `PositionLot` documents keyed by composite `(exchange_id, account_id, broker_lot_id)`
- `BrokerEvent` documents store full normalized transaction history
- Closed-trade backfill (`_closed_trade_backfill` in `oanda_account_sync.py`) ensures historical completeness

---

## 4. Linkage Diagram (Mermaid)

```mermaid
erDiagram
    %% Core domain entities
    POSITION_LOT {
        string broker_lot_id PK "OANDA trade.id"
        string entry_batch_id "batchID of opening txn"
        string last_event_id "most recent txn id"
        list closing_event_ids "txn ids that closed/reduced"
        ChildOrder stop_loss
        ChildOrder take_profit
        dict raw_broker "original OANDA trade"
    }

    CHILD_ORDER {
        string broker_order_id PK "OANDA order.id"
        string trade_id FK "parent PositionLot"
        string filling_event_id "txn that filled it — event-driven (§10)"
        string cancelling_event_id "txn that cancelled it — event-driven (§10)"
    }

    BROKER_EVENT {
        string broker_event_id PK "OANDA txn.id"
        string broker_lot_id FK "tradeID (resolved from tradeClosed etc.)"
        string broker_order_id FK "orderID"
        string batch_id "atomic group (ORDER_FILL + TRADE_OPENED)"
        string request_id "client correlation"
        string instrument
        float qty, price, pl
    }

    %% OANDA native entities (not stored, only normalized from)
    OANDA_TRADE ||--o{ POSITION_LOT : "normalized to"
    OANDA_TRADE ||--o{ CHILD_ORDER : "stopLossOrder / takeProfitOrder"
    OANDA_TRANSACTION ||--|| BROKER_EVENT : "normalized to"
    OANDA_ORDER ||--o{ CHILD_ORDER : "pending or child"

    %% Relationships & cross-references
    POSITION_LOT ||--o{ CHILD_ORDER : "embeds (stop_loss, take_profit)"
    POSITION_LOT ||--o{ BROKER_EVENT : "entry_batch_id, last_event_id, closing_event_ids"
    BROKER_EVENT ||--o{ POSITION_LOT : "broker_lot_id"
    BROKER_EVENT ||--o{ CHILD_ORDER : "filling_event_id, cancelling_event_id"

    %% API surfaces used only for validation / bootstrap
    OANDA_POSITION ||--o{ INSTRUMENT_EXPOSURE : "validated against (aggregate only)"
    ACCOUNT_DETAILS ||--|| "lastTransactionID" : "cursor for incremental sync"
    ACCOUNT_DETAILS ||--|{ OANDA_TRADE : "open trades only"
    ACCOUNT_DETAILS ||--o{ OANDA_ORDER : "pending orders"
    ACCOUNT_DETAILS ||--o{ OANDA_POSITION : "current positions (aggregate)"

    %% Sync flow
    POLL_CHANGES ||--|| BROKER_EVENT : "produces"
    LIST_TRANSACTIONS ||--|| BROKER_EVENT : "produces"
```

**Legend**
- Solid arrows = direct containment or primary mapping
- Dashed / FK = cross-reference via ID fields
- OANDA_* boxes = wire format only (never persisted as-is)
- `batch_id` groups multi-transaction atomic operations (critical for reconciliation)

---

## 5. ID Flow Example — Market Order Fill (Happy Path)

1. **Client** calls `place_market_order` → OANDA returns `orderFillTransactionID` in response.
2. **Transaction stream** (via `/changes` or range query) delivers:
   - `ORDER_FILL` txn: contains `orderID`, `tradeOpened { tradeID, ... }`, `batchID`
   - `TRADE_OPENED` txn: contains `tradeID`, `batchID` (same), `initialMarginRequired`
3. `normalize_oanda_transaction` extracts:
   - `trade_id` (from `tradeOpened` or nested `tradeClosed`)
   - `order_id`
   - `batch_id`
4. `event_from_oanda_transaction` creates one or more `BrokerEvent`s with both `broker_lot_id` and `broker_order_id`.
5. `lot_from_oanda_trade` creates `PositionLot`:
   - `broker_lot_id = tradeID`
   - If `stopLossOrder` present → `ChildOrder` with `trade_id`, `filling_event_id`, etc.
6. Cursor advanced to new `lastTransactionID`.
7. On close (SL hit, manual, etc.):
   - New `TRADE_CLOSED` / `ORDER_FILL` txns appear
   - `closingTransactionIDs` on the closed trade object
   - `BrokerEvent`s written with `broker_lot_id`
   - `PositionLot` updated with `state=closed`, `closing_event_ids`, `realized_pl`

All IDs remain **string** (OANDA uses string transaction IDs despite being numeric).

---

## 6. Positions vs Trades — Why Positions Are Secondary

- OANDA **Positions** endpoint returns aggregate `long` / `short` units per instrument (netted).
- BrokerAI **never** uses Positions as source of truth for lots.
- `validate_exposure` (adapter) performs a periodic reconciliation check: materialized `instrument_exposure` rollups per `(symbol, direction)` vs the Positions aggregate (falls back to summing open lots when rollups are empty).
- Mismatches are logged at WARNING and returned on `SyncResult.exposure_mismatches`; automatic repair is not triggered in Phase 1.
- This design allows strategy-level attribution, partial closes, and per-trade P&L that aggregate Positions cannot provide.

---

## 7. Efficiency Observations & Recommendations

**Strengths (current design)**
- Transaction-cursor incremental sync (`sinceTransactionID`) is optimal — minimal API calls, strong consistency via `lastTransactionID`.
- `batch_id` preserves OANDA atomicity guarantees.
- Full `raw_broker` + complete transaction history enables deep audit and replay.
- `ChildOrder` embedding keeps SL/TP state co-located (no N+1 queries).

**Potential Efficiencies / Review Items**
1. **Positions endpoint is narrowly used** — only `validate_exposure` + a few sync paths. Consider deriving exposure purely from lots (already authoritative) and remove the call, or promote it to a continuous cheap health check.
2. **Account Details already contains everything needed for bootstrap** (`trades`, `orders`, `positions`, `lastTransactionID`). Some paths still perform separate `list_all_trades(state=CLOSED)` calls. Opportunity to consolidate into a single documented bootstrap sequence.
3. **Materialized `InstrumentExposure`** — `instrument_exposure` collection, recomputed after each sync (§10).
4. **Transaction volume** — tiered TTL for low-value admin types; trade-linked events retained indefinitely (§12).
5. **Closed trade history** — always requires a separate call or backfill. No single endpoint returns complete trade + current state. Document this limitation for future broker adapters.
6. **ID namespace** — `ids.py` helpers added; raw OANDA strings remain primary keys until a second adapter lands (§12).
7. **Child order lifecycle events** — event-driven FSM in `child_orders.py` (§10).

---

## 8. File Reference Summary

| Layer | File | Key Functions / Classes |
|-------|------|-------------------------|
| API client | `src/brokerai/integrations/oanda_client.py` | `OandaHttpClient`, rate limiting, keep-alive |
| Normalization | `src/brokerai/integrations/oanda.py` | All `_normalize_*`, `list_*`, `iter_transactions_*`, `poll_account_changes` |
| Domain models | `src/brokerai/trading/broker/models.py` | `PositionLot`, `ChildOrder`, `BrokerEvent`, `InstrumentExposure` |
| Child orders | `src/brokerai/trading/broker/child_orders.py` | `apply_child_orders_from_events`, `reconcile_child_order` |
| Event retention | `src/brokerai/trading/broker/event_retention.py` | `classify_event_retention`, `collect_protected_event_ids` |
| Broker IDs | `src/brokerai/trading/broker/ids.py` | `broker_lot_key`, `broker_event_key`, parse helpers |
| Close reason | `src/brokerai/trading/broker/close_reason.py` | `enrich_lot_from_events`, `infer_close_reason` |
| Adapter | `src/brokerai/trading/broker/adapters/oanda.py` | `OandaAdapter`, `lot_from_oanda_trade`, `validate_exposure` |
| State | `src/brokerai/trading/oanda_account_state.py` | `lots_from_account_details`, `apply_account_changes` |
| Sync | `src/brokerai/trading/broker/sync.py` | `run_broker_sync` — unified orchestrator |
| Bootstrap | `src/brokerai/trading/oanda_bootstrap.py` | `run_oanda_bootstrap` — canonical bootstrap sequence |
| Cursor repair | `src/brokerai/trading/oanda_cursor_repair.py` | `repair_stale_cursor_if_needed`, `repair_transaction_gap` |
| Account sync (wrapper) | `src/brokerai/trading/oanda_account_sync.py` | Thin wrapper → `run_broker_sync` |
| Persistence | `src/brokerai/db/repositories/broker_lots.py`, `broker_events.py`, `instrument_exposure.py` | CRUD for lots, events & exposure rollups |

---

## 9. Phase 1 Upgrades (Implemented)

Foundation + sync consolidation (2026-07):

### Unified orchestrator

All OANDA polling flows through `run_broker_sync` in [`src/brokerai/trading/broker/sync.py`](../../src/brokerai/trading/broker/sync.py). The former parallel `run_oanda_account_sync` loop in the web app was removed; `run_oanda_account_sync` is now a thin wrapper for backward-compatible callers (secretary bot, settings cache).

### Canonical bootstrap (`run_oanda_bootstrap`)

One documented sequence in [`src/brokerai/trading/oanda_bootstrap.py`](../../src/brokerai/trading/oanda_bootstrap.py):

1. `get_account_details` → open lots + `lastTransactionID`
2. `list_all_trades(state=CLOSED)` → closed history
3. `iter_transactions_idrange(1→lastTransactionID)` → event backfill (streamed via `event_sink` when called from `run_broker_sync`)

Bootstrap writes **lots + events + cursor** and sets `account_bootstrap_at`. Production bootstrap streams one OANDA page at a time to bound memory.

### Incremental sync

Single `/changes` poll per tick via `sync_incremental_from_changes`. No `/openTrades` or `/positions` on every tick. Live prices fetched only when `fetch_live_prices=True` (broker monitor).

### Positions health check

`validate_exposure` runs on bootstrap and at most once per `oanda_exposure_check_interval_seconds` (default 3600s). Mismatches are logged; lots remain authoritative.

### Cursor repair

`repair_stale_cursor_if_needed` shared between bootstrap and incremental paths (`oanda_cursor_repair.py`).

### Deferred to Phase 2 (completed — see §10)

Materialized `InstrumentExposure`, event TTL/bulk upsert, multi-broker ID namespace, full child-order state machine.

---

## 10. Phase 2 Upgrades (Implemented)

Semantic linkage + exposure materialization (2026-07):

### Child-order state machine

[`src/brokerai/trading/broker/child_orders.py`](../../src/brokerai/trading/broker/child_orders.py) adds `apply_child_orders_from_events` and `reconcile_child_order`. Wired into `run_broker_sync` after `enrich_lot_from_events`:

- Trade snapshots remain primary; events validate/backfill `PENDING → FILLED/CANCELLED` transitions
- `filling_event_id` / `cancelling_event_id` actively joined against `BrokerEvent` stream
- `infer_close_reason` inspects closing txn types when embedded SL/TP state is `CANCELLED`
- Linkage validation logs mismatches between fill txn IDs and `closing_event_ids`

### Order-level `/changes` ingestion

`apply_account_changes` now processes `ordersCreated`, `ordersFilled`, and `ordersCancelled` into child-order patches merged into affected lots before upsert.

### Event repository indexes

`BrokerEventsRepository.list_events_by_order_id` + index `(exchange_id, account_id, broker_order_id, time)`.

### Materialized `InstrumentExposure`

Collection `instrument_exposure` keyed by `(exchange_id, account_id, symbol, direction)`. Recomputed idempotently at end of each `run_broker_sync`. Consumed by:

- `validate_exposure` local side (via rollups, with open-lot fallback)
- `GET /api/trades/exposure`
- Dashboard open-exposure panel on the exchange overview

### API + UI

- `stop_loss`, `take_profit`, `partial_close` registered in trade reason registry
- Trade detail panel shows fill/cancel txn IDs on embedded child orders

---

## 11. Permanently Deferred

| Item | Notes |
|------|-------|
| Trailing-stop broker order churn | Strategy exits remain strategy-driven (`trail_ema_slow` / `trail_atr` market close) |
| Separate `child_orders` collection | Embedded model + `broker_events` audit trail is sufficient |

---

## 12. Phase 3 Upgrades (Implemented)

Performance, retention, and multi-broker prep (2026-07):

### Bulk event upsert

[`BrokerEventsRepository.upsert_events_bulk`](../../src/brokerai/db/repositories/broker_events.py) uses `pymongo.bulk_write` with `UpdateOne` + `$setOnInsert` for `created_at`. `upsert_events` delegates to the bulk path. Batch size: `BROKERAI_BROKER_EVENTS_BULK_BATCH_SIZE` (default 500).

### Transaction pagination

[`list_transactions_idrange`](../../src/brokerai/integrations/oanda.py) and [`list_transactions_since`](../../src/brokerai/integrations/oanda.py) follow OANDA `pages[]` URLs so bootstrap and cursor repair fetch all transactions (not capped at 500 per response). [`iter_transactions_idrange`](../../src/brokerai/integrations/oanda.py) yields per-page batches for memory-bounded bootstrap.

### Streaming bootstrap

[`run_oanda_bootstrap`](../../src/brokerai/trading/oanda_bootstrap.py) accepts an optional `event_sink(batch, protected_event_ids)` callback. When provided (always from [`run_broker_sync`](../../src/brokerai/trading/broker/sync.py) bootstrap path), step 3 bulk-upserts each page via `BrokerEventsRepository.upsert_events` and returns `events_streamed=True` with an empty in-memory `events` list. Lot enrichment after bootstrap reads events from MongoDB via `list_events_for_lot`. Stale-cursor repair events still merge into a single end-of-sync upsert.

### Single-write repair contract

[`repair_transaction_gap`](../../src/brokerai/trading/oanda_cursor_repair.py) and [`repair_stale_cursor_if_needed`](../../src/brokerai/trading/oanda_cursor_repair.py) return events only; [`run_broker_sync`](../../src/brokerai/trading/broker/sync.py) is the sole persistence point (eliminates double upsert on gap repair).

### Tiered event retention

[`event_retention.py`](../../src/brokerai/trading/broker/event_retention.py) classifies events:

| Tier | Criteria | Retention |
|------|----------|-----------|
| Trade-linked | `broker_lot_id` / `broker_order_id` set, or type in `TRADE_LINKED_EVENT_TYPES` | Indefinite |
| Low-value | No linkage + type in `LOW_VALUE_EVENT_TYPES` (e.g. `MARGIN_CALL`, `DAILY_FINANCING`) | `retention_expires_at` = event time + 90 days |

Settings: `BROKERAI_BROKER_EVENTS_RETENTION_ENABLED` (default true), `BROKERAI_BROKER_EVENTS_LOW_VALUE_RETENTION_DAYS` (default 90). Partial TTL index on `retention_expires_at`. Protected event IDs from open lots and incomplete closed lots skip TTL assignment. Re-upsert clears `retention_expires_at` via `$unset` when an event becomes trade-linked or protected.

### Multi-broker ID helpers + connection prep

- [`ids.py`](../../src/brokerai/trading/broker/ids.py): `broker_lot_key`, `broker_event_key`, `parse_broker_lot_key`, `parse_broker_event_key` — logging/cross-broker use only; MongoDB fields remain raw broker strings.
- [`ExchangeConnectionsRepository.get_connection`](../../src/brokerai/db/repositories/exchange_connections.py) / `save_connection` / `delete_connection` — generic CRUD; `get_oanda()` remains a thin wrapper.
- [`BrokerStateService._credentials_for`](../../src/brokerai/trading/broker/state.py) replaces OANDA-only credential resolution.
- Lot lookups prefer `(exchange_id, account_id, broker_lot_id)` when `account_id` is known.

### Multi-broker ID namespace contract

When a second broker adapter is added, surrogate keys use `{exchange_id}:{broker_lot_id}` and `{exchange_id}:{broker_event_id}` for cross-broker uniqueness. MongoDB compound unique indexes remain `(exchange_id, account_id, broker_lot_id)` — no OANDA data migration until a second adapter ships.

---

**End of document.**  
For questions on a specific ID resolution path or to request a sequence diagram of a failure/reconciliation scenario, open an issue referencing this file.