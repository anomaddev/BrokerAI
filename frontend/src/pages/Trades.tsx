import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ExternalLink, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import {
  api,
  BACKGROUND_TASK_COMPLETED_EVENT,
  TRADE_SYNC_TASK_KIND,
  type BackgroundTaskCompletedDetail,
  type Trade,
  type TradeReconciliation,
} from "../api/client";
import { useBackgroundTasks } from "../context/BackgroundTasksContext";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import TradeDetailOverlay from "../components/trades/TradeDetailOverlay";
import {
  directionClassName,
  directionLabel,
  DEFAULT_TRADE_SORT_COLUMN,
  DEFAULT_TRADE_SORT_DIRECTION,
  defaultTradeSortDirection,
  exploreHrefForTrade,
  formatPrice,
  formatPnl,
  formatUnits,
  orderPrice,
  pnlClassName,
  sortTradesForTable,
  tradeDuration,
  tradeExitPrice,
  tradeIsOpen,
  tradeLastModifiedAt,
  tradeRealizedPl,
  tradeReasonCell,
  tradeStatusKey,
  tradeStatusClassName,
  tradeStatusLabel,
  type TradeSortColumn,
  type TradeSortDirection,
} from "../lib/trades";

const POLL_INTERVAL_MS = 15_000;
const TRADE_LIMIT = 200;

type StatusFilter = "all" | "open" | "closed";

type TradeTableSort = {
  column: TradeSortColumn;
  direction: TradeSortDirection;
};

const INITIAL_TRADE_TABLE_SORT: TradeTableSort = {
  column: DEFAULT_TRADE_SORT_COLUMN,
  direction: DEFAULT_TRADE_SORT_DIRECTION,
};

const SORTABLE_COLUMNS: { key: TradeSortColumn; label: string }[] = [
  { key: "status", label: "Status" },
  { key: "last_modified", label: "Last modified" },
  { key: "strategy", label: "Strategy" },
  { key: "pair", label: "Pair" },
  { key: "direction", label: "Direction" },
  { key: "entry", label: "Entry" },
  { key: "price", label: "Price" },
  { key: "pnl", label: "P/L" },
  { key: "stop_loss", label: "SL" },
  { key: "take_profit", label: "TP" },
  { key: "units", label: "Units" },
  { key: "reason", label: "Reason" },
  { key: "duration", label: "Duration" },
];

function SortableTradeHeader({
  column,
  label,
  sortColumn,
  sortDirection,
  onSort,
}: {
  column: TradeSortColumn;
  label: string;
  sortColumn: TradeSortColumn;
  sortDirection: TradeSortDirection;
  onSort: (column: TradeSortColumn) => void;
}) {
  const isActive = sortColumn === column;
  return (
    <th scope="col">
      <button
        type="button"
        className={[
          "trades-table-sort-btn",
          isActive ? "trades-table-sort-btn--active" : undefined,
        ]
          .filter(Boolean)
          .join(" ")}
        onClick={() => onSort(column)}
        aria-sort={
          isActive ? (sortDirection === "asc" ? "ascending" : "descending") : "none"
        }
      >
        <span>{label}</span>
        <span className="trades-table-sort-indicator" aria-hidden="true">
          {isActive ? (sortDirection === "asc" ? "↑" : "↓") : "↕"}
        </span>
      </button>
    </th>
  );
}

export default function Trades() {
  const { formatInstant } = useGeneralSettings();
  const { isTaskKindActive, watchBackgroundTasks, showFooterNotice } = useBackgroundTasks();
  const [trades, setTrades] = useState<Trade[]>([]);
  const [reconciliation, setReconciliation] = useState<TradeReconciliation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [strategyFilter, setStrategyFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [pairQuery, setPairQuery] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);
  const [tableSort, setTableSort] = useState<TradeTableSort>(INITIAL_TRADE_TABLE_SORT);
  const selectAllRef = useRef<HTMLInputElement>(null);
  const syncing = isTaskKindActive(TRADE_SYNC_TASK_KIND);

  const handleSortColumn = useCallback((column: TradeSortColumn) => {
    setTableSort((current) => {
      if (current.column === column) {
        return {
          column,
          direction: current.direction === "asc" ? "desc" : "asc",
        };
      }
      return {
        column,
        direction: defaultTradeSortDirection(column),
      };
    });
  }, []);

  const sortedTrades = useMemo(
    () =>
      sortTradesForTable(trades, {
        sortColumn: tableSort.column,
        sortDirection: tableSort.direction,
        statusFilter,
        reconciliation,
      }),
    [trades, tableSort, statusFilter, reconciliation],
  );

  const tradeIds = useMemo(() => sortedTrades.map((trade) => trade.id), [sortedTrades]);
  const selectedVisibleCount = useMemo(
    () => tradeIds.filter((id) => selectedIds.has(id)).length,
    [tradeIds, selectedIds],
  );
  const allTradesSelected = tradeIds.length > 0 && selectedVisibleCount === tradeIds.length;
  const someTradesSelected =
    selectedVisibleCount > 0 && selectedVisibleCount < tradeIds.length;

  const tableStrategies = useMemo(() => {
    const byId = new Map<string, string>();
    for (const trade of trades) {
      if (trade.strategy_id) {
        byId.set(trade.strategy_id, trade.strategy_name);
      }
    }
    return [...byId.entries()]
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [trades]);

  const loadTrades = useCallback(async () => {
    const params: {
      status: StatusFilter;
      limit: number;
      strategy_id?: string;
      pair?: string;
    } = {
      status: statusFilter,
      limit: TRADE_LIMIT,
    };
    if (strategyFilter !== "all") params.strategy_id = strategyFilter;
    const trimmedPair = pairQuery.trim();
    if (trimmedPair) params.pair = trimmedPair;
    const data = await api.listTrades(params);
    setTrades(data.trades);
  }, [statusFilter, strategyFilter, pairQuery]);

  const loadReconciliation = useCallback(async () => {
    const data = await api.getTradeReconciliation();
    setReconciliation(data);
  }, []);

  const toggleSelected = useCallback((tradeId: string) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(tradeId)) {
        next.delete(tradeId);
      } else {
        next.add(tradeId);
      }
      return next;
    });
  }, []);

  const toggleSelectAllTrades = useCallback(() => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allTradesSelected) {
        for (const id of tradeIds) {
          next.delete(id);
        }
      } else {
        for (const id of tradeIds) {
          next.add(id);
        }
      }
      return next;
    });
  }, [allTradesSelected, tradeIds]);

  const handleSyncTrades = useCallback(async () => {
    try {
      await api.syncTrades();
      watchBackgroundTasks();
    } catch (err) {
      showFooterNotice({
        label: "Sync broker state",
        message: err instanceof Error ? err.message : "Failed to start trade sync",
        status: "failed",
      });
    }
  }, [watchBackgroundTasks, showFooterNotice]);

  useEffect(() => {
    const checkbox = selectAllRef.current;
    if (!checkbox) return;
    checkbox.indeterminate = someTradesSelected;
    checkbox.checked = allTradesSelected;
  }, [allTradesSelected, someTradesSelected]);

  useEffect(() => {
    setSelectedIds((current) => {
      const visible = new Set(tradeIds);
      const next = new Set([...current].filter((id) => visible.has(id)));
      return next.size === current.size ? current : next;
    });
  }, [tradeIds]);

  useEffect(() => {
    function onTaskCompleted(event: Event) {
      const detail = (event as CustomEvent<BackgroundTaskCompletedDetail>).detail;
      if (detail.kind !== TRADE_SYNC_TASK_KIND) {
        return;
      }

      void Promise.all([loadTrades(), loadReconciliation()]);
    }

    window.addEventListener(BACKGROUND_TASK_COMPLETED_EVENT, onTaskCompleted);
    return () => window.removeEventListener(BACKGROUND_TASK_COMPLETED_EVENT, onTaskCompleted);
  }, [loadTrades, loadReconciliation]);

  useEffect(() => {
    if (strategyFilter === "all") return;
    if (!tableStrategies.some((strategy) => strategy.id === strategyFilter)) {
      setStrategyFilter("all");
    }
  }, [tableStrategies, strategyFilter]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        await Promise.all([loadTrades(), loadReconciliation()]);
        if (!cancelled) setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load trades");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    setLoading(true);
    load();

    const interval = window.setInterval(load, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [loadTrades, loadReconciliation]);

  return (
    <div className="trades-page">
      <div
        className={[
          "trades-section",
          selectedTrade ? "trades-section--detail-open" : undefined,
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {selectedTrade && (
          <TradeDetailOverlay
            trade={selectedTrade}
            reconciliation={reconciliation}
            onClose={() => setSelectedTrade(null)}
          />
        )}

        {!selectedTrade && (
          <>
            <h1 className="page-title">Trades</h1>
            <p className="settings-muted trades-page-lead">
              Open and closed trades from the BrokerAI ledger, with broker reconciliation.
            </p>

            <div className="trades-toolbar">
              <div className="trades-toolbar-filters">
          <div className="research-select-wrap trades-status-select-wrap">
            <select
              className="research-select"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as StatusFilter)}
              aria-label="Filter by status"
            >
              <option value="all">All statuses</option>
              <option value="open">Open</option>
              <option value="closed">Closed</option>
            </select>
          </div>
          <input
            type="search"
            className="research-search"
            placeholder="Filter by pair…"
            value={pairQuery}
            onChange={(event) => setPairQuery(event.target.value)}
            aria-label="Filter by pair"
          />
          <div className="research-select-wrap">
            <select
              className="research-select"
              value={strategyFilter}
              onChange={(event) => setStrategyFilter(event.target.value)}
              aria-label="Filter by strategy"
            >
              <option value="all">All strategies</option>
              {tableStrategies.map((strategy) => (
                <option key={strategy.id} value={strategy.id}>
                  {strategy.name}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm trades-sync-btn"
            disabled={loading || syncing}
            onClick={() => void handleSyncTrades()}
          >
            <RefreshCw size={14} strokeWidth={1.75} aria-hidden="true" />
            {syncing ? "Syncing…" : "Sync from OANDA"}
          </button>
              </div>
            </div>

            <div className="settings-panel settings-panel--trades">
              {loading && <p className="settings-muted">Loading trades…</p>}
              {error && !loading && <p className="settings-error">{error}</p>}
              {!loading && !error && trades.length === 0 && (
                <p className="settings-muted">No trades yet.</p>
              )}

              {!loading && !error && trades.length > 0 && (
                <div className="research-table-wrap">
                  <table className="research-table trades-table">
                <thead>
                  <tr>
                    <th className="trades-table-checkbox-col" scope="col">
                      <label className="trades-table-checkbox-label">
                        <input
                          ref={selectAllRef}
                          type="checkbox"
                          className="ui-checkbox-input"
                          checked={allTradesSelected}
                          onChange={toggleSelectAllTrades}
                          aria-label="Select all visible trades"
                        />
                      </label>
                    </th>
                    {SORTABLE_COLUMNS.map((column) => (
                      <SortableTradeHeader
                        key={column.key}
                        column={column.key}
                        label={column.label}
                        sortColumn={tableSort.column}
                        sortDirection={tableSort.direction}
                        onSort={handleSortColumn}
                      />
                    ))}
                    <th className="research-actions-col" scope="col" aria-hidden="true" />
                  </tr>
                </thead>
                <tbody>
                  {sortedTrades.map((trade, index) => {
                    const status = tradeStatusKey(trade);
                    const isOpen = status === "open";
                    const isCancelled = status === "cancelled";
                    const prevTrade = index > 0 ? sortedTrades[index - 1] : null;
                    const isFirstClosed =
                      statusFilter === "all" &&
                      !isOpen &&
                      (prevTrade == null || tradeIsOpen(prevTrade));
                    const market =
                      isOpen && reconciliation
                        ? reconciliation.ledger_market[trade.id]
                        : undefined;
                    const lastModified = tradeLastModifiedAt(trade);
                    const exitPrice = tradeExitPrice(trade);
                    const realizedPl = tradeRealizedPl(trade);
                    const reason = tradeReasonCell(trade);
                    const isSelected = selectedIds.has(trade.id);
                    return (
                      <tr
                        key={trade.id}
                        className={[
                          "trades-table-row--clickable",
                          isFirstClosed ? "trades-row--section-start" : undefined,
                          isSelected ? "trades-table-row--selected" : undefined,
                        ]
                          .filter(Boolean)
                          .join(" ")}
                        aria-selected={isSelected}
                        onClick={() => setSelectedTrade(trade)}
                      >
                        <td
                          className="trades-table-checkbox-col"
                          onClick={(event) => event.stopPropagation()}
                        >
                          <label className="trades-table-checkbox-label">
                            <input
                              type="checkbox"
                              className="ui-checkbox-input"
                              checked={isSelected}
                              onChange={() => toggleSelected(trade.id)}
                              aria-label={`Select ${trade.pair} ${trade.direction} trade`}
                            />
                          </label>
                        </td>
                        <td>
                          <span className={tradeStatusClassName(status)}>
                            {tradeStatusLabel(status)}
                          </span>
                        </td>
                        <td className="settings-muted">
                          {lastModified ? formatInstant(lastModified, "compact") : "—"}
                        </td>
                        <td>{trade.strategy_name}</td>
                        <td>{trade.pair}</td>
                        <td>
                          <span className={directionClassName(trade.direction)}>
                            {directionLabel(trade.direction)}
                          </span>
                        </td>
                        <td>{formatPrice(trade.entry_price)}</td>
                        <td>
                          {isOpen ? formatPrice(market?.current_price) : formatPrice(exitPrice)}
                        </td>
                        <td
                          className={
                            isOpen
                              ? pnlClassName(market?.unrealized_pl)
                              : pnlClassName(realizedPl)
                          }
                        >
                          {isOpen ? formatPnl(market?.unrealized_pl) : formatPnl(realizedPl)}
                        </td>
                        <td>{formatPrice(orderPrice(trade.stop_loss, trade.stop_loss_price))}</td>
                        <td>{formatPrice(orderPrice(trade.take_profit, trade.take_profit_price))}</td>
                        <td>{formatUnits(trade.units)}</td>
                        <td className="trades-reason-cell" title={reason.title}>
                          <span className="trades-reason-text">{reason.display}</span>
                        </td>
                        <td>
                          {isOpen
                            ? "—"
                            : isCancelled
                              ? "—"
                              : tradeDuration(trade.opened_at, trade.closed_at ?? null)}
                        </td>
                        <td
                          className="research-actions-cell"
                          onClick={(event) => event.stopPropagation()}
                        >
                          <div className="research-row-actions">
                            <Link
                              to={exploreHrefForTrade(trade)}
                              className="research-action-btn"
                              title="Explore pair"
                              aria-label={`Explore ${trade.pair}`}
                            >
                              <ExternalLink size={15} strokeWidth={1.75} />
                            </Link>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
