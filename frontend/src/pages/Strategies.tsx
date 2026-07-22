import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, ChevronUp, History, Minus, Plus, Trash2, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import {
  api,
  type AiStrategyStartupJob,
  type AssetClass,
  type Strategy,
  type StrategyExecutionPhase,
} from "../api/client";
import { ROUTES } from "../lib/routes";
import AssetClassFilterSelect from "../components/AssetClassFilterSelect";
import CreateStrategyOverlay from "../components/strategies/CreateStrategyOverlay";
import QueueBacktestOverlay, {
  type QueueBacktestParams,
} from "../components/strategies/QueueBacktestOverlay";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import { startupStatusLabel } from "../lib/aiStrategy/activityLabels";
import {
  backtestStatusLabel,
  normalizeBacktestStatus,
} from "../lib/strategies/backtestStatus";
import {
  sortStrategies,
  strategyTimeframeLabel,
  strategyTypeLabel,
  type SortDirection,
  type StrategySortKey,
} from "../lib/strategies/strategyListSort";
import {
  ASSET_CLASS_LABELS,
  instrumentSelectionSummary,
  isWatchlistAllSelection,
} from "./strategies/strategyAssignment";

function instrumentSummary(strategy: Strategy): string {
  const summary = instrumentSelectionSummary(strategy.instrument_selection);
  if (summary) return summary;

  const count = strategy.instruments.length;
  if (count === 0) {
    const selection = strategy.instrument_selection;
    if (selection) {
      const watchlistClasses = Object.entries(selection)
        .filter(([, syms]) => isWatchlistAllSelection(syms))
        .map(([cls]) => ASSET_CLASS_LABELS[cls as AssetClass]);
      if (watchlistClasses.length > 0) {
        return watchlistClasses.map((label) => `${label} watchlist`).join(", ");
      }
    }
    return "—";
  }
  const unit = strategy.asset_class === "forex" ? "pair" : "symbol";
  return `${count} ${unit}${count === 1 ? "" : "s"}`;
}

function formatWinRate(rate: number | null): string {
  if (rate === null) return "—";
  return `${(rate * 100).toFixed(1)}%`;
}

function formatPnl(value: number): string {
  const formatted = Math.abs(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (value > 0) return `+$${formatted}`;
  if (value < 0) return `-$${formatted}`;
  return "$0.00";
}

function pnlClass(value: number): string {
  if (value > 0) return "strategy-stat--positive";
  if (value < 0) return "strategy-stat--negative";
  return "strategy-stat--neutral";
}

function executionPhaseLabel(phase: StrategyExecutionPhase): string {
  if (phase === "warming") return "Warming";
  if (phase === "ready") return "Ready";
  return "Live";
}


function isAiStrategy(strategy: Strategy): boolean {
  return strategy.preset_id === "ai_strategy";
}

function warmupProgressLabel(strategy: Strategy): string | null {
  if (strategy.preset_id !== "ai_strategy") return null;
  if (strategy.execution_phase !== "warming" && strategy.execution_phase !== "ready") {
    return null;
  }
  const completed = Number(strategy.warmup?.completed_days ?? 0);
  const targetRaw = strategy.warmup?.target_days;
  const target =
    targetRaw == null || Number(targetRaw) <= 0 ? "?" : String(Math.max(1, Number(targetRaw)));
  return `${completed}/${target} ET days`;
}

function normalizeStrategies(apiStrategies: Strategy[]): Strategy[] {
  return apiStrategies.map((strategy) => ({
    ...strategy,
    strategy_type: strategy.strategy_type ?? (strategy.preset_id ? "preset" : "custom"),
    backtest_status: normalizeBacktestStatus(strategy.backtest_status),
  }));
}

type SortableHeaderProps = {
  label: string;
  sortKey: StrategySortKey;
  activeKey: StrategySortKey;
  direction: SortDirection;
  onSort: (key: StrategySortKey) => void;
};

function SortableHeader({ label, sortKey, activeKey, direction, onSort }: SortableHeaderProps) {
  const active = activeKey === sortKey;
  return (
    <th scope="col" aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : "none"}>
      <button
        type="button"
        className={`strategy-table-sort-btn${active ? " strategy-table-sort-btn--active" : ""}`}
        onClick={() => onSort(sortKey)}
      >
        <span>{label}</span>
        {active ? (
          direction === "asc" ? (
            <ChevronUp size={14} aria-hidden />
          ) : (
            <ChevronDown size={14} aria-hidden />
          )
        ) : null}
      </button>
    </th>
  );
}

export type StrategiesListVariant = "standard" | "ai";

type StrategiesProps = {
  variant?: StrategiesListVariant;
};

export default function Strategies({ variant = "standard" }: StrategiesProps) {
  const navigate = useNavigate();
  const { formatInstant } = useGeneralSettings();
  const isAiList = variant === "ai";
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [assetClassFilter, setAssetClassFilter] = useState<Set<AssetClass>>(new Set());
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkPending, setBulkPending] = useState(false);
  const [bulkError, setBulkError] = useState<string | null>(null);
  const [actionsOpen, setActionsOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [backtestOverlayOpen, setBacktestOverlayOpen] = useState(false);
  const [backtestOverlayError, setBacktestOverlayError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<StrategySortKey>("name");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const [promotingId, setPromotingId] = useState<string | null>(null);
  const [startupJobs, setStartupJobs] = useState<Record<string, AiStrategyStartupJob>>({});
  const selectAllRef = useRef<HTMLInputElement>(null);
  const actionsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .listStrategies()
      .then((data) => {
        const all = normalizeStrategies(data.strategies);
        setStrategies(
          isAiList ? all.filter(isAiStrategy) : all.filter((strategy) => !isAiStrategy(strategy)),
        );
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load strategies");
        setStrategies([]);
      })
      .finally(() => setLoading(false));
  }, [isAiList]);

  useEffect(() => {
    if (!isAiList) {
      setStartupJobs({});
      return;
    }
    const aiIds = strategies.filter(isAiStrategy).map((strategy) => strategy.id);
    if (aiIds.length === 0) {
      setStartupJobs({});
      return;
    }

    let cancelled = false;

    async function loadStartupJobs() {
      const entries = await Promise.all(
        aiIds.map(async (id) => {
          try {
            const response = await api.getStrategyStartup(id);
            return [id, response.job] as const;
          } catch {
            return [id, null] as const;
          }
        }),
      );
      if (cancelled) return;
      const next: Record<string, AiStrategyStartupJob> = {};
      for (const [id, job] of entries) {
        if (job) next[id] = job;
      }
      setStartupJobs(next);
    }

    void loadStartupJobs();
    const timer = window.setInterval(() => {
      void loadStartupJobs();
    }, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [strategies, isAiList]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matched = strategies.filter((strategy) => {
      if (assetClassFilter.size > 0 && !assetClassFilter.has(strategy.asset_class)) {
        return false;
      }
      if (!q) return true;
      const haystack = [
        strategy.name,
        strategy.asset_class_label,
        strategy.description,
        strategyTypeLabel(strategy),
        ...strategy.instruments,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
    return sortStrategies(matched, sortKey, sortDirection);
  }, [strategies, query, assetClassFilter, sortKey, sortDirection]);

  function handleBuildClick() {
    if (isAiList) {
      navigate(ROUTES.research.strategyNew("ai-strategy"));
      return;
    }
    setCreateOpen(true);
  }

  const filteredIds = useMemo(() => filtered.map((strategy) => strategy.id), [filtered]);
  const selectedFilteredCount = useMemo(
    () => filteredIds.filter((id) => selectedIds.has(id)).length,
    [filteredIds, selectedIds],
  );
  const allFilteredSelected =
    filteredIds.length > 0 && selectedFilteredCount === filteredIds.length;
  const someFilteredSelected =
    selectedFilteredCount > 0 && selectedFilteredCount < filteredIds.length;

  useEffect(() => {
    const checkbox = selectAllRef.current;
    if (!checkbox) return;
    checkbox.indeterminate = someFilteredSelected;
    checkbox.checked = allFilteredSelected;
  }, [allFilteredSelected, someFilteredSelected]);

  useEffect(() => {
    if (!actionsOpen) return;

    function handleClick(event: MouseEvent) {
      if (actionsRef.current && !actionsRef.current.contains(event.target as Node)) {
        setActionsOpen(false);
      }
    }

    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") setActionsOpen(false);
    }

    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [actionsOpen]);

  useEffect(() => {
    if (selectedFilteredCount === 0) {
      setActionsOpen(false);
    }
  }, [selectedFilteredCount]);

  function toggleSelected(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function toggleSelectAllFiltered() {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allFilteredSelected) {
        for (const id of filteredIds) {
          next.delete(id);
        }
      } else {
        for (const id of filteredIds) {
          next.add(id);
        }
      }
      return next;
    });
  }

  function clearSelection() {
    setSelectedIds(new Set());
    setBulkError(null);
  }

  function handleSort(key: StrategySortKey) {
    if (sortKey === key) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDirection("asc");
  }

  async function applyBulkEnabled(enabled: boolean) {
    const ids = filteredIds.filter((id) => selectedIds.has(id));
    if (ids.length === 0) return;

    setBulkPending(true);
    setBulkError(null);

    try {
      const results = await Promise.allSettled(
        ids.map((id) => api.updateStrategy(id, { enabled })),
      );
      const failed = results.filter((result) => result.status === "rejected").length;
      if (failed > 0) {
        setBulkError(
          failed === ids.length
            ? `Could not ${enabled ? "enable" : "disable"} selected strategies.`
            : `${failed} of ${ids.length} strategies could not be updated.`,
        );
      }

      const updatedIds = new Set(
        results
          .map((result, index) => (result.status === "fulfilled" ? ids[index] : null))
          .filter((id): id is string => id !== null),
      );

      if (updatedIds.size > 0) {
        setStrategies((current) =>
          current.map((strategy) =>
            updatedIds.has(strategy.id) ? { ...strategy, enabled } : strategy,
          ),
        );
      }
    } catch (err) {
      setBulkError(err instanceof Error ? err.message : "Bulk update failed");
    } finally {
      setBulkPending(false);
    }
  }

  async function applyBulkDelete() {
    const ids = filteredIds.filter((id) => selectedIds.has(id));
    if (ids.length === 0) return;

    setBulkPending(true);
    setBulkError(null);

    try {
      const results = await Promise.allSettled(ids.map((id) => api.deleteStrategy(id)));
      const failed = results.filter((result) => result.status === "rejected").length;
      if (failed > 0) {
        setBulkError(
          failed === ids.length
            ? "Could not delete selected strategies."
            : `${failed} of ${ids.length} strategies could not be deleted.`,
        );
      }

      const deletedIds = new Set(
        results
          .map((result, index) => (result.status === "fulfilled" ? ids[index] : null))
          .filter((id): id is string => id !== null),
      );

      if (deletedIds.size > 0) {
        setStrategies((current) => current.filter((strategy) => !deletedIds.has(strategy.id)));
        setSelectedIds((current) => {
          const next = new Set(current);
          for (const id of deletedIds) {
            next.delete(id);
          }
          return next;
        });
      }

      setDeleteConfirmOpen(false);
    } catch (err) {
      setBulkError(err instanceof Error ? err.message : "Bulk delete failed");
    } finally {
      setBulkPending(false);
    }
  }

  const selectedStrategiesForBacktest = useMemo(
    () => filtered.filter((strategy) => selectedIds.has(strategy.id)),
    [filtered, selectedIds],
  );

  function openBacktestOverlay() {
    setActionsOpen(false);
    setBacktestOverlayError(null);
    setBulkError(null);
    setBacktestOverlayOpen(true);
  }

  async function applyBulkBacktest(params: QueueBacktestParams) {
    const ids = selectedStrategiesForBacktest.map((strategy) => strategy.id);
    if (ids.length === 0) return;

    setBulkPending(true);
    setBacktestOverlayError(null);
    setBulkError(null);

    try {
      const result = await api.queueStrategyBacktests(ids, {
        name: params.name,
        instrument: params.instrument,
        period: params.period,
        verbose: params.verbose,
        account_margin: params.account_margin,
      });
      const updatedById = new Map(
        normalizeStrategies(result.strategies).map((strategy) => [strategy.id, strategy]),
      );
      setStrategies((current) =>
        current.map((strategy) => updatedById.get(strategy.id) ?? strategy),
      );
      setBacktestOverlayOpen(false);
      if (result.queued < ids.length) {
        setBulkError(
          `${result.queued} of ${ids.length} strategies were queued for backtest.`,
        );
      }
    } catch (err) {
      setBacktestOverlayError(err instanceof Error ? err.message : "Could not queue backtests");
    } finally {
      setBulkPending(false);
    }
  }

  function openDeleteConfirm() {
    setActionsOpen(false);
    setDeleteConfirmOpen(true);
  }

  function stopDialogActivation(event: React.MouseEvent | React.KeyboardEvent) {
    event.stopPropagation();
  }

  function openStrategy(strategy: Strategy) {
    if (isAiStrategy(strategy)) {
      navigate(ROUTES.research.aiStrategyView(strategy.id));
      return;
    }
    navigate(ROUTES.research.strategyEdit(strategy.id));
  }

  async function promoteStrategy(strategy: Strategy) {
    if (strategy.execution_phase !== "ready" || promotingId) return;
    setPromotingId(strategy.id);
    setBulkError(null);
    try {
      const updated = await api.promoteStrategy(strategy.id);
      setStrategies((current) =>
        current.map((row) => (row.id === updated.id ? { ...row, ...updated } : row)),
      );
    } catch (err) {
      setBulkError(err instanceof Error ? err.message : "Could not promote strategy");
    } finally {
      setPromotingId(null);
    }
  }

  const hasFilteredResults = filtered.length > 0;
  const hasSelection = selectedFilteredCount > 0;
  const emptyMessage = loading
    ? isAiList
      ? "Loading AI strategies…"
      : "Loading strategies…"
    : error
      ? error
      : strategies.length === 0
        ? isAiList
          ? "No AI Strategies yet. Build one for a single forex pair — it starts enabled, runs reports and backtests, then learns in shadow until you promote it."
          : "No strategies yet. Use Build Strategy to create your first one."
        : "No strategies match your filters.";

  return (
    <div>
      <div className="strategy-list-header">
        <h1 className="page-title">{isAiList ? "AI Strategies" : "Strategies"}</h1>
        <button type="button" className="btn" onClick={handleBuildClick}>
          <Plus size={16} aria-hidden />
          {isAiList ? "Build AI Strategy" : "Build Strategy"}
        </button>
      </div>

      <div className="settings-panel strategy-saved-panel">
        <div className="research-filters">
          <input
            type="search"
            className="research-search"
            placeholder="Search by name, type, asset class, or instrument…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <AssetClassFilterSelect value={assetClassFilter} onChange={setAssetClassFilter} />
          <div
            className={`research-multiselect strategy-bulk-actions-menu${
              hasSelection ? " strategy-bulk-actions-menu--active" : ""
            }`}
            ref={actionsRef}
          >
            <div className="research-multiselect-wrap">
              <button
                type="button"
                className="research-multiselect-trigger strategy-bulk-actions-trigger"
                disabled={!hasSelection || bulkPending}
                onClick={() => setActionsOpen((prev) => !prev)}
                aria-haspopup="menu"
                aria-expanded={actionsOpen}
                aria-label="Strategy bulk actions"
              >
                {hasSelection ? `Actions (${selectedFilteredCount})` : "Actions"}
              </button>
            </div>
            {actionsOpen && hasSelection ? (
              <div className="strategy-bulk-actions-dropdown" role="menu">
                <p className="strategy-bulk-actions-dropdown-header">
                  {selectedFilteredCount} selected
                </p>
                <button
                  type="button"
                  className="strategy-bulk-action-item strategy-bulk-action-item--enable"
                  role="menuitem"
                  disabled={bulkPending}
                  onClick={() => {
                    setActionsOpen(false);
                    void applyBulkEnabled(true);
                  }}
                >
                  <span className="strategy-bulk-action-icon" aria-hidden>
                    <Check size={15} strokeWidth={2.25} />
                  </span>
                  Enable selected
                </button>
                <button
                  type="button"
                  className="strategy-bulk-action-item strategy-bulk-action-item--disable"
                  role="menuitem"
                  disabled={bulkPending}
                  onClick={() => {
                    setActionsOpen(false);
                    void applyBulkEnabled(false);
                  }}
                >
                  <span className="strategy-bulk-action-icon" aria-hidden>
                    <Minus size={15} strokeWidth={2.25} />
                  </span>
                  Disable selected
                </button>
                <button
                  type="button"
                  className="strategy-bulk-action-item strategy-bulk-action-item--backtest"
                  role="menuitem"
                  disabled={bulkPending}
                  onClick={openBacktestOverlay}
                >
                  <span className="strategy-bulk-action-icon" aria-hidden>
                    <History size={15} strokeWidth={2.25} />
                  </span>
                  Run Backtest
                </button>
                <div className="strategy-bulk-actions-divider" role="separator" />
                <button
                  type="button"
                  className="strategy-bulk-action-item strategy-bulk-action-item--clear"
                  role="menuitem"
                  disabled={bulkPending}
                  onClick={() => {
                    setActionsOpen(false);
                    clearSelection();
                  }}
                >
                  <span className="strategy-bulk-action-icon" aria-hidden>
                    <X size={15} strokeWidth={2.25} />
                  </span>
                  Clear selection
                </button>
                <div className="strategy-bulk-actions-divider" role="separator" />
                <button
                  type="button"
                  className="strategy-bulk-action-item strategy-bulk-action-item--delete"
                  role="menuitem"
                  disabled={bulkPending}
                  onClick={openDeleteConfirm}
                >
                  <span className="strategy-bulk-action-icon" aria-hidden>
                    <Trash2 size={15} strokeWidth={2.25} />
                  </span>
                  Delete selected
                </button>
              </div>
            ) : null}
          </div>
        </div>

        {bulkError && !loading && <p className="settings-error">{bulkError}</p>}

        <div className="research-table-wrap">
          <table className="research-table strategy-table">
            <thead>
              <tr>
                <th className="strategy-table-checkbox-col" scope="col">
                  <label className="strategy-table-checkbox-label">
                    <input
                      ref={selectAllRef}
                      type="checkbox"
                      className="ui-checkbox-input"
                      checked={allFilteredSelected}
                      onChange={toggleSelectAllFiltered}
                      disabled={!hasFilteredResults}
                      aria-label="Select all visible strategies"
                    />
                  </label>
                </th>
                <SortableHeader
                  label="Strategy"
                  sortKey="name"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Timeframe"
                  sortKey="timeframe"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Type"
                  sortKey="type"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Asset class"
                  sortKey="assetClass"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Status"
                  sortKey="status"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Backtest"
                  sortKey="backtest"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
                <th scope="col">Instruments</th>
                <SortableHeader
                  label="Trades"
                  sortKey="trades"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Win rate"
                  sortKey="winRate"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Realized P&L"
                  sortKey="pnl"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Open"
                  sortKey="open"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Last trade"
                  sortKey="lastTrade"
                  activeKey={sortKey}
                  direction={sortDirection}
                  onSort={handleSort}
                />
              </tr>
            </thead>
            <tbody>
              {!hasFilteredResults ? (
                <tr className="strategy-table-empty-row">
                  <td colSpan={13}>
                    <div className="strategy-table-empty">
                      <p className={error && !loading ? "settings-error" : "settings-muted"}>
                        {emptyMessage}
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                filtered.map((strategy) => {
                  const isSelected = selectedIds.has(strategy.id);
                  const backtestStatus = normalizeBacktestStatus(strategy.backtest_status);
                  return (
                    <tr
                      key={strategy.id}
                      className={[
                        strategy.route ? "strategy-table-row--clickable" : undefined,
                        isSelected ? "strategy-table-row--selected" : undefined,
                      ]
                        .filter(Boolean)
                        .join(" ") || undefined}
                      onClick={() => openStrategy(strategy)}
                      onKeyDown={(e) => {
                        if (strategy.route && (e.key === "Enter" || e.key === " ")) {
                          e.preventDefault();
                          openStrategy(strategy);
                        }
                      }}
                      tabIndex={strategy.route ? 0 : undefined}
                      role={strategy.route ? "link" : undefined}
                      aria-selected={isSelected}
                    >
                      <td
                        className="strategy-table-checkbox-col"
                        onClick={(e) => e.stopPropagation()}
                        onKeyDown={(e) => e.stopPropagation()}
                      >
                        <label className="strategy-table-checkbox-label">
                          <input
                            type="checkbox"
                            className="ui-checkbox-input"
                            checked={isSelected}
                            onChange={() => toggleSelected(strategy.id)}
                            aria-label={`Select ${strategy.name}`}
                          />
                        </label>
                      </td>
                      <td>
                        <div className="strategy-name-cell">
                          <span className="strategy-name">{strategy.name}</span>
                          {strategy.description ? (
                            <span className="strategy-description">{strategy.description}</span>
                          ) : null}
                        </div>
                      </td>
                      <td>{strategyTimeframeLabel(strategy)}</td>
                      <td>
                        <span
                          className={`research-tag strategy-type-tag strategy-type-tag--${
                            strategy.strategy_type === "preset" ? "template" : "custom"
                          }`}
                        >
                          {strategyTypeLabel(strategy)}
                        </span>
                      </td>
                      <td>{strategy.asset_class_label}</td>
                      <td>
                        <div className="strategy-status-cell">
                          <span
                            className={`research-tag strategy-status--${
                              strategy.enabled ? "enabled" : "disabled"
                            }`}
                          >
                            {strategy.enabled ? "Enabled" : "Disabled"}
                          </span>
                          {strategy.execution_phase ? (
                            <span
                              className={`research-tag strategy-phase--${strategy.execution_phase}`}
                              title={
                                warmupProgressLabel(strategy)
                                  ? `Warm-up ${warmupProgressLabel(strategy)}`
                                  : undefined
                              }
                            >
                              {executionPhaseLabel(strategy.execution_phase)}
                              {warmupProgressLabel(strategy)
                                ? ` · ${warmupProgressLabel(strategy)}`
                                : ""}
                            </span>
                          ) : null}
                          {startupJobs[strategy.id] ? (
                            <span
                              className={`research-tag strategy-startup--${startupJobs[strategy.id].status}`}
                              title={startupJobs[strategy.id].error || undefined}
                            >
                              {startupStatusLabel(startupJobs[strategy.id])}
                            </span>
                          ) : null}
                          {strategy.execution_phase === "ready" ? (
                            <button
                              type="button"
                              className="btn btn-sm strategy-promote-btn"
                              disabled={promotingId === strategy.id || bulkPending}
                              onClick={(event) => {
                                event.stopPropagation();
                                void promoteStrategy(strategy);
                              }}
                            >
                              {promotingId === strategy.id ? "Promoting…" : "Promote"}
                            </button>
                          ) : null}
                        </div>
                      </td>
                      <td>
                        <span className={`research-tag strategy-backtest--${backtestStatus}`}>
                          {backtestStatusLabel(backtestStatus)}
                        </span>
                      </td>
                      <td className="settings-muted">{instrumentSummary(strategy)}</td>
                      <td>{strategy.stats.total_trades}</td>
                      <td>{formatWinRate(strategy.stats.win_rate)}</td>
                      <td className={pnlClass(strategy.stats.realized_pnl)}>
                        {formatPnl(strategy.stats.realized_pnl)}
                      </td>
                      <td>{strategy.stats.open_positions}</td>
                      <td className="settings-muted">
                        {formatInstant(strategy.stats.last_trade_at, "short")}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {createOpen ? <CreateStrategyOverlay onClose={() => setCreateOpen(false)} /> : null}

      {backtestOverlayOpen ? (
        <QueueBacktestOverlay
          strategies={selectedStrategiesForBacktest}
          submitting={bulkPending}
          error={backtestOverlayError}
          onClose={() => {
            if (!bulkPending) {
              setBacktestOverlayOpen(false);
              setBacktestOverlayError(null);
            }
          }}
          onConfirm={applyBulkBacktest}
        />
      ) : null}

      {deleteConfirmOpen && (
        <div
          className="confirm-overlay"
          role="presentation"
          onClick={() => !bulkPending && setDeleteConfirmOpen(false)}
        >
          <div
            className="confirm-dialog confirm-dialog--error"
            role="alertdialog"
            aria-labelledby="delete-strategies-title"
            aria-describedby="delete-strategies-message"
            onClick={stopDialogActivation}
          >
            <h4 id="delete-strategies-title">
              Delete {selectedFilteredCount === 1 ? "strategy" : "strategies"}?
            </h4>
            <p id="delete-strategies-message">
              This will permanently delete{" "}
              <strong>
                {selectedFilteredCount} strateg{selectedFilteredCount === 1 ? "y" : "ies"}
              </strong>
              . This cannot be undone.
            </p>
            <div className="confirm-actions">
              <button
                type="button"
                className="btn btn-secondary"
                disabled={bulkPending}
                onClick={() => setDeleteConfirmOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={bulkPending}
                onClick={() => void applyBulkDelete()}
              >
                {bulkPending ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
