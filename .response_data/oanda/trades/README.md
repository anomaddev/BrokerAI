# OANDA Trades API Response Samples

Captured example payloads from the OANDA v20 REST API for account trade listing. These files live under `.response_data/` (gitignored) for local reference when building or debugging BrokerAI trade sync and normalization.

| File | Size | Trades | States | Status |
|------|------|--------|--------|--------|
| `open_trades.json` | ~3 KB | 3 | OPEN only | Dedicated open snapshot |
| `closed_trades.json` | ~64 KB | 88 | CLOSED only | Dedicated closed history |
| `all_trades.json` | ~67 KB | 91 | OPEN + CLOSED | Combined list (3 open + 88 closed) |

All three responses share `lastTransactionID: "566"`, indicating they were captured from the same account on or after 2026-07-02.

---

## How the Three Files Relate

```
all_trades.json (91 trades)
├── 3 OPEN trades   ──≈── open_trades.json (same IDs, marginUsed drifts slightly)
└── 88 CLOSED trades ═══ closed_trades.json (byte-identical per trade)
```

| Relationship | Result |
|--------------|--------|
| Open IDs ⊆ All IDs | ✓ `{559, 562, 565}` |
| Closed IDs ⊆ All IDs | ✓ all 88 closed IDs present |
| Open ∩ Closed | ∅ (no overlap) |
| All = Open ∪ Closed | ✓ exactly 91 = 3 + 88 |
| Closed payload match | ✓ every closed trade in `all_trades.json` matches `closed_trades.json` exactly |
| Open payload match | ≈ same structure; only `marginUsed` differs (see below) |

**Sort order in `all_trades.json`:** Newest-first by trade ID, with **all OPEN trades grouped at the top** (IDs 565 → 562 → 559), then CLOSED trades continuing the descending ID sequence (553 → 550 → … → 61). State transitions once at index 3 (559 OPEN → 553 CLOSED).

**Open-trade drift:** The three open positions are the same in both files, but `marginUsed` differs by ~0.0004–0.0016 per trade — likely two requests seconds apart as mark-to-market margin recalculated:

| Trade ID | `open_trades.json` marginUsed | `all_trades.json` marginUsed |
|----------|-------------------------------|------------------------------|
| 565 | 39.0474 | 39.0478 |
| 562 | 51.9651 | 51.9667 |
| 559 | 32.2238 | 32.2242 |

Unrealized P/L, prices, units, and stop-loss orders are identical between the two open snapshots.

---

## Likely API Endpoints

Based on OANDA v20 documentation and BrokerAI's integration layer (`src/brokerai/integrations/oanda.py`):

| File | Probable endpoint | Notes |
|------|-------------------|-------|
| `open_trades.json` | `GET /v3/accounts/{accountID}/openTrades` | Used by `list_open_trades()` |
| `closed_trades.json` | `GET /v3/accounts/{accountID}/trades?state=CLOSED` | Closed-trade history (paginated) |
| `all_trades.json` | `GET /v3/accounts/{accountID}/trades` | No state filter; returns open + closed in one list |

Single-trade detail uses `GET /v3/accounts/{accountID}/trades/{tradeID}` and returns `{ "trade": { ... } }` (wrapper not present in these list responses).

With 91 total trades, this capture fits in a **single page** if `count ≥ 91` (OANDA default is often 50 — larger accounts need `beforeID` pagination).

---

## Top-Level Envelope

All three files use the same list envelope:

```json
{
  "trades": [ /* Trade objects */ ],
  "lastTransactionID": "566"
}
```

- **`trades`** — Array of trade objects. Ordering varies by endpoint (see below).
- **`lastTransactionID`** — OANDA's monotonic transaction cursor for the account. Useful for change polling and correlating with order/fill transactions.

No other top-level keys appear in these captures (no explicit pagination cursor in the response body — pagination uses request params).

---

## `all_trades.json` — Combined Trade List

**Count:** 91 trades (3 OPEN + 88 CLOSED)  
**Trade ID range:** 61 – 565  
**Date range:** 2026-02-02 → 2026-07-02  

This is the **canonical superset** sample: one response containing both state shapes. Use it when implementing generic trade-list parsing that must branch on `state`.

### Structure at a glance

```
Index   ID    State    Instrument   Notes
─────   ───   ─────    ──────────   ─────
0       565   OPEN     EUR_JPY      Current short; SL pending
1       562   OPEN     CAD_JPY      Current short; SL pending
2       559   OPEN     AUD_JPY      Current short; SL pending
3       553   CLOSED   EUR_JPY      SL filled
4       550   CLOSED   CAD_JPY      SL filled
…       …     CLOSED   …            …
90      61    CLOSED   …            Oldest trade in capture
```

### Aggregate totals (from `all_trades.json`)

| Metric | OPEN (3) | CLOSED (88) |
|--------|----------|-------------|
| Unrealized P/L | −1.0348 | — |
| Realized P/L | 0.0000 | −42.7590 |
| Margin used | 123.24 | — |
| Wins / losses | — | 34 / 53 / 1 flat |

### Union schema (all possible trade keys)

Because `all_trades.json` mixes states, its trade objects collectively expose **every field** seen across open and closed payloads:

```
averageClosePrice, closeTime, closingTransactionIDs, currentUnits,
dividendAdjustment, financing, id, initialMarginRequired, initialUnits,
instrument, marginUsed, openTime, price, realizedPL, state,
stopLossOrder, takeProfitOrder, trueUnrealizedPL, unrealizedPL
```

**Parsing rule:** treat fields as **state-dependent**, not required on every row. A CLOSED trade will not include `unrealizedPL`; an OPEN trade will not include `closeTime`. Code that iterates `all_trades.json` must switch on `state` before accessing state-specific fields.

### Example: OPEN trade in combined list

Same shape as `open_trades.json` — trade 565 at index 0:

```json
{
  "id": "565",
  "instrument": "EUR_JPY",
  "state": "OPEN",
  "initialUnits": "-683",
  "currentUnits": "-683",
  "price": "184.196",
  "unrealizedPL": "-0.1798",
  "trueUnrealizedPL": "-0.1798",
  "marginUsed": "39.0478",
  "stopLossOrder": { "type": "STOP_LOSS", "state": "PENDING", "..." : "..." }
}
```

### Example: CLOSED trade immediately following open block

Trade 553 at index 3 — first CLOSED entry after the open group:

```json
{
  "id": "553",
  "instrument": "EUR_JPY",
  "state": "CLOSED",
  "initialUnits": "-768",
  "currentUnits": "0",
  "realizedPL": "-0.7153",
  "closeTime": "2026-07-01T07:57:16.870490095Z",
  "averageClosePrice": "185.502",
  "closingTransactionIDs": ["555"],
  "stopLossOrder": { "type": "STOP_LOSS", "state": "FILLED", "..." : "..." }
}
```

No `unrealizedPL`, `marginUsed`, or `trueUnrealizedPL` on this row.

### When to use this file vs the split files

| Use case | Best file |
|----------|-----------|
| Test mixed-state list parsing / pagination | `all_trades.json` |
| Test open-trade normalization only | `open_trades.json` (smaller) |
| Test closed-trade edge cases (partial close, brackets) | `closed_trades.json` (same closed data, no open noise) |
| Minimal AI context for open positions | `open_trades.json` |

---

## `open_trades.json` — Open Trades Snapshot

**Endpoint:** `GET .../openTrades`  
**Captured:** 2026-07-02 (~20:27 UTC)  
**Count:** 3 open trades  
**Aggregate unrealized P/L:** −1.0348  
**Aggregate margin used:** 123.24  

### Summary

All three positions are **short** JPY cross pairs opened within ~250 ms of each other (likely a batch entry). Each has an attached **stop-loss order** in `PENDING` state. No take-profit orders. All show small unrealized losses at capture time.

| Trade ID | Instrument | Direction | Units | Entry Price | Unrealized P/L | Margin Used | Stop Loss |
|----------|------------|-----------|-------|-------------|----------------|-------------|-----------|
| 565 | EUR_JPY | Short | 683 | 184.196 | −0.1798 | 39.05 | 185.530 |
| 562 | CAD_JPY | Short | 1,474 | 113.572 | −0.6099 | 51.97 | 114.460 |
| 559 | AUD_JPY | Short | 931 | 111.501 | −0.2451 | 32.22 | 112.235 |

### Field presence (OPEN trades)

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | OANDA trade ID |
| `instrument` | string | e.g. `EUR_JPY` |
| `price` | string | Entry fill price (3 dp for JPY pairs) |
| `openTime` | string | ISO-8601 UTC with nanosecond precision |
| `initialUnits` | string | Signed lot size; negative = short |
| `initialMarginRequired` | string | Margin at open |
| `state` | string | `"OPEN"` |
| `currentUnits` | string | Matches `initialUnits` (no partial close) |
| `realizedPL` | string | `"0.0000"` |
| `financing` | string | `"0.0000"` |
| `dividendAdjustment` | string | `"0.0000"` |
| `trueUnrealizedPL` | string | Mark-to-market P/L |
| `unrealizedPL` | string | Same as `trueUnrealizedPL` here |
| `marginUsed` | string | Current margin (live; drifts between requests) |
| `stopLossOrder` | object | Attached SL child order |

**Absent on OPEN trades:** `closeTime`, `averageClosePrice`, `closingTransactionIDs`, `takeProfitOrder`.

### Embedded `stopLossOrder` (OPEN)

```json
{
  "id": "566",
  "createTime": "2026-07-02T20:27:24.111844157Z",
  "type": "STOP_LOSS",
  "tradeID": "565",
  "price": "185.530",
  "timeInForce": "GTC",
  "triggerCondition": "DEFAULT",
  "triggerMode": "TOP_OF_BOOK",
  "state": "PENDING"
}
```

- **`triggerMode: "TOP_OF_BOOK"`** — SL triggers on top-of-book pricing.
- **`state: "PENDING"`** — Order is live.
- Stop price is **above** entry for shorts (loss if price rises).

### BrokerAI normalization mapping

`list_open_trades()` → `_normalize_oanda_open_trade()` extracts:

- `id`, `instrument`, `pair`, `units` (abs), `direction`, `price`, `unrealized_pl`, `open_time`
- Does **not** surface `stopLossOrder`, `marginUsed`, or `trueUnrealizedPL`.

`get_broker_open_trades_snapshot()` additionally fetches live pricing and attaches `current_price`.

---

## `closed_trades.json` — Closed Trade History

**Endpoint:** `GET .../trades?state=CLOSED`  
**Date range:** 2026-02-02 → 2026-07-01  
**Count:** 88 closed trades  
**Trade ID range:** 61 – 553  
**Aggregate realized P/L:** −42.76  
**Win / loss / flat:** 34 / 53 / 1  

Identical to the CLOSED portion of `all_trades.json` (indices 3–90).

### Instrument coverage

25 distinct instruments:

| Instrument | Count | Sum realized P/L |
|------------|-------|------------------|
| EUR_JPY | 6 | +5.26 |
| AUD_JPY | 6 | −0.65 |
| USD_CHF | 6 | −3.55 |
| NZD_USD | 6 | −0.72 |
| USD_CAD | 5 | −39.02 |
| GBP_USD | 5 | −1.02 |
| GBP_CHF | 5 | −0.70 |
| AUD_USD | 5 | −0.23 |
| CAD_JPY | 4 | −1.32 |
| CHF_JPY | 4 | +0.24 |
| EUR_USD | 4 | −1.01 |
| EUR_GBP | 4 | −1.31 |
| AUD_CHF | 4 | +0.97 |
| USD_JPY | 3 | −0.05 |
| AUD_CAD | 3 | +0.00 |
| EUR_CHF | 3 | +0.06 |
| *(9 more pairs with 1–2 trades each)* | | |

**Direction split:** 46 long, 42 short.  
**Position sizing:** `initialUnits` from 1 to 77,584 (median 100).

### Field presence (CLOSED trades)

| Field | Type | Description |
|-------|------|-------------|
| `state` | string | `"CLOSED"` |
| `currentUnits` | string | Always `"0"` |
| `realizedPL` | string | Final P/L including partial closes |
| `closeTime` | string | When the trade fully closed |
| `averageClosePrice` | string | VWAP of all closing fills |
| `closingTransactionIDs` | string[] | One or more fill transaction IDs |
| `stopLossOrder` | object? | Present on 14/88 trades |
| `takeProfitOrder` | object? | Present on 5/88 trades |

**Absent on CLOSED trades:** `unrealizedPL`, `trueUnrealizedPL`, `marginUsed`.

**Non-zero financing:** 13/88 trades. Example: trade 417 (EUR_JPY) has `financing: "0.0204"`.

### Close mechanics

| Pattern | Count | Meaning |
|---------|-------|---------|
| No attached orders | 74 | Manual close or orders not in list payload |
| Stop-loss **FILLED** | 4 | Closed by stop hit |
| Stop-loss **CANCELLED** | 10 | SL removed when trade closed another way |
| Take-profit **CANCELLED** | 5 | TP removed at close (none filled) |
| Both SL + TP attached | 5 | Bracket entries; both cancelled at manual close |

**Take-profit fills:** 0 — no TP reached `FILLED` state.

### Hold duration

- **Minimum:** ~20 seconds (trade 527, CAD_JPY)
- **Median:** ~2.9 hours
- **Maximum:** ~4.8 days

### Notable edge cases

#### 1. Multiple closing transactions

| Trade ID | Instrument | closingTransactionIDs | realizedPL |
|----------|------------|----------------------|------------|
| 439 | EUR_JPY | `["523", "540"]` | +0.1908 |
| 434 | EUR_JPY | `["518", "523"]` | +0.1467 |

Partial closes before final exit. `realizedPL` on the CLOSED object is authoritative.

#### 2. Stop-loss filled vs cancelled

When SL fills:
```json
"state": "FILLED",
"fillingTransactionID": "555",
"filledTime": "2026-07-01T07:57:16.870490095Z",
"tradeClosedIDs": ["553"]
```
`filledTime` matches trade `closeTime`. Manual closes show SL `state: "CANCELLED"` with matching `cancelledTime`.

#### 3. Bracket orders (SL + TP)

Trade 514 (AUD_JPY): TP at 111.822, SL at 112.129 (short). Both **cancelled** at manual close for +0.0152 P/L.

#### 4. Extreme position size and loss

Trade 476 (USD_CAD): −77,584 units, realizedPL −38.5701. SL at 1.42223 **FILLED**.

#### 5. Best and worst performers

| Trade ID | Instrument | realizedPL | Notes |
|----------|------------|------------|-------|
| 417 | EUR_JPY | +5.6556 | Largest win; includes financing |
| 106 | AUD_CHF | +1.0248 | |
| 343 | NZD_USD | +0.7200 | |
| 476 | USD_CAD | −38.5701 | SL fill; oversized units |
| 96 | USD_CHF | −1.6272 | |
| 102 | GBP_CHF | −0.8677 | |

#### 6. Break-even close

Trade 69 (USD_CAD): entry and `averageClosePrice` both 1.36514, `realizedPL: "0.0000"`.

#### 7. Price precision

- **JPY-quoted pairs:** 3 dp (e.g. `184.196`)
- **Other majors:** 5 dp (e.g. `1.42154`)

Matches `oanda_price_precision()` in BrokerAI.

### BrokerAI normalization mapping

`_normalize_oanda_closed_trade()` extracts:

- `id`, `instrument`, `pair`, `units`, `direction`, `entry_price`, `exit_price`, `realized_pl`, `open_time`, `close_time`, `closed_at`

**Not extracted:** `financing`, `closingTransactionIDs`, attached order details, `initialMarginRequired`.

---

## Schema Comparison: OPEN vs CLOSED

```
                    OPEN                    CLOSED
                    ────                    ──────
state               OPEN                    CLOSED
currentUnits        signed (≠ 0)            "0"
realizedPL          "0.0000"                final P/L
unrealizedPL        present                 absent
trueUnrealizedPL    present                 absent
marginUsed          present                 absent
closeTime           absent                  present
averageClosePrice   absent                  present
closingTransactionIDs absent                present (1+ IDs)
stopLossOrder       PENDING (open snapshot) FILLED | CANCELLED | absent
takeProfitOrder     absent (open snapshot)  CANCELLED | absent
financing           "0.0000" (open)         may be non-zero
```

In `all_trades.json`, expect **both shapes in one array** — always branch on `state` first.

---

## Stringly-Typed Numeric Fields

OANDA returns most numeric values as **strings**:

- Prices: 3 or 5 dp depending on instrument
- P/L and margin: 4 dp (`"0.0000"`, `"-0.1798"`)
- Units: integer strings, signed (`"-683"`, `"100"`)

BrokerAI parsers use `_optional_float()` and explicit `float()` casts.

---

## Timestamp Format

UTC ISO-8601 with **nanosecond** fractional seconds:

```
2026-07-02T20:27:24.111844157Z
```

`_parse_broker_timestamp()` must truncate or tolerate 9-digit fractions.

---

## Implications for BrokerAI Development

1. **Three endpoints, two shapes** — `openTrades` returns OPEN only; `trades?state=CLOSED` returns CLOSED only; `trades` (no filter) returns both. Implement parsing once with a `state` switch.

2. **List vs detail** — These are list endpoints (`trades[]`). Single-trade GET wraps in `{ "trade": ... }`.

3. **Sort order differs by capture** — `all_trades.json` groups OPEN first, then CLOSED descending. Filtered endpoints may return different ordering; do not assume sort order for deduplication.

4. **Live fields drift** — `marginUsed` (and potentially unrealized P/L) can differ between back-to-back requests. Do not use these files to assert exact margin equality across endpoints.

5. **Attached orders are optional** — 84% of closed trades have **no** embedded SL/TP. Use `state`, `closeTime`, and `realizedPL` for close detection.

6. **Close reason inference** — Reliable only when `stopLossOrder.state === "FILLED"` or `takeProfitOrder.state === "FILLED"`.

7. **Partial closes** — Multiple `closingTransactionIDs` mean staged reduction before final close.

8. **Financing** — Present on longer-held trades; not mapped in `_normalize_oanda_closed_trade()` today.

9. **Pagination** — 91 trades fit one page at `count=91`. Production accounts may need `beforeID` loops; test with truncated copies if needed.

---

## Related Source Files

| Path | Role |
|------|------|
| `src/brokerai/integrations/oanda.py` | `list_open_trades`, `_normalize_oanda_open_trade`, `_normalize_oanda_closed_trade`, `parse_oanda_close_response` |
| `tests/test_oanda_open_trades.py` | Unit tests with inline dict fixtures |
| `tests/test_oanda_candles.py` | Candle parsing (separate endpoint family) |

---

## Re-capture Checklist

When refreshing these samples:

1. Redact account ID if sharing outside local `.response_data/`.
2. Note capture timestamp and `lastTransactionID` for all three files.
3. Record query params (`state`, `count`, `beforeID`).
4. Capture `all_trades.json` with `count` high enough to include all trades, or paginate and merge.
5. Expect minor drift on live fields (`marginUsed`, `unrealizedPL`) between sequential requests.
6. For AI prompts, prefer `open_trades.json` (3 trades) or a trimmed slice over the full 91-trade dump.
