import { useEffect, useMemo, useRef, useState, type UIEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ChevronDown, ChevronLeft, ChevronRight, FileDown, Maximize2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  api,
  type BacktestAction,
  type BacktestLog,
  type BacktestRun,
  type BacktestSettings,
  type CandleBar,
  type Strategy,
} from "../api/client";
import ExploreCandleChart from "../components/explore/ExploreCandleChart";
import StrategyOverlay from "../components/strategies/StrategyOverlay";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import { decomposeStrategyToLayers } from "../lib/chart/chartOverlayState";
import { buildCenteredBarFocusWindow } from "../lib/chart/chartFocusWindow";
import { parseAppInstant } from "../lib/formatTime";
import { ROUTES } from "../lib/routes";
import {
  backtestActionToSelectedMarker,
  backtestActionsToChartMarkers,
} from "../lib/backtests/backtestChartMarkers";
import {
  findEventIndex,
  type EventStepKind,
} from "../lib/backtests/backtestActionStep";
import { downloadBacktestFeedbackPdf } from "../lib/backtests/exportBacktestFeedbackPdf";
import {
  backtestRunStatusLabel,
  normalizeBacktestRunStatus,
} from "../lib/backtests/backtestRunStatus";
import { TIMEFRAME_LABELS, type Timeframe } from "../lib/strategyParams";
import {
  applySuggestionsToParams,
  suggestionDisplayValue,
  storeBacktestAiDraft,
  type AiFeedbackSuggestion,
} from "../lib/backtests/applyAiSuggestions";
import type { StrategyParamsV1 } from "../lib/strategyParams";
import { getSupabaseBrowserClient } from "../lib/supabaseClient";

type PanelTab = "overview" | "strategy" | "actions" | "feedback";
type TimeStepMode = "1d" | "7d" | "1m";

const EVENT_STEP_OPTIONS: Array<{ kind: EventStepKind; label: string }> = [
  { kind: "action", label: "Action" },
  { kind: "signal", label: "Signal" },
  { kind: "exit", label: "Exit" },
];

type EventStepMenuProps = {
  direction: "next" | "previous";
  kind: EventStepKind;
  disabled?: boolean;
  onKindChange: (kind: EventStepKind) => void;
  onStep: (kind: EventStepKind) => void;
};

function EventStepMenu({
  direction,
  kind,
  disabled = false,
  onKindChange,
  onStep,
}: EventStepMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const kindLabel = EVENT_STEP_OPTIONS.find((option) => option.kind === kind)?.label ?? "Action";

  useEffect(() => {
    if (!open) return;

    function handlePointer(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  return (
    <div
      className={`backtest-step-menu${open ? " backtest-step-menu--open" : ""}`}
      ref={rootRef}
    >
      <div className="backtest-step-split">
        <button
          type="button"
          className="btn btn-secondary btn-sm backtest-step-split-main"
          disabled={disabled}
          onClick={() => onStep(kind)}
        >
          {direction === "previous" ? (
            <ChevronLeft className="backtest-step-icon" size={16} strokeWidth={2.25} aria-hidden />
          ) : null}
          <span>
            {direction === "next" ? "Next" : "Previous"} {kindLabel}
          </span>
          {direction === "next" ? (
            <ChevronRight className="backtest-step-icon" size={16} strokeWidth={2.25} aria-hidden />
          ) : null}
        </button>
        <button
          type="button"
          className="btn btn-secondary btn-sm backtest-step-split-chevron"
          disabled={disabled}
          aria-expanded={open}
          aria-haspopup="menu"
          aria-label={`${direction === "next" ? "Next" : "Previous"} step options`}
          onClick={() => setOpen((value) => !value)}
        >
          <ChevronDown
            className={`backtest-step-icon backtest-step-icon--menu${open ? " backtest-step-icon--open" : ""}`}
            size={15}
            strokeWidth={2.25}
            aria-hidden
          />
        </button>
      </div>
      {open ? (
        <div className="backtest-step-dropdown" role="menu">
          <p className="backtest-step-dropdown-header">
            {direction === "next" ? "Step forward in time to" : "Step back in time to"}
          </p>
          {EVENT_STEP_OPTIONS.map((option) => (
            <button
              key={option.kind}
              type="button"
              role="menuitem"
              className={`backtest-step-dropdown-item${
                option.kind === kind ? " backtest-step-dropdown-item--active" : ""
              }`}
              onClick={() => {
                onKindChange(option.kind);
                onStep(option.kind);
                setOpen(false);
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function formatWinRate(rate: number | null | undefined): string {
  if (rate == null) return "—";
  return `${(rate * 100).toFixed(1)}%`;
}

function formatPnl(value: number | null | undefined): string {
  if (value == null) return "—";
  const formatted = Math.abs(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (value > 0) return `+$${formatted}`;
  if (value < 0) return `-$${formatted}`;
  return "$0.00";
}

function formatDrawdown(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function formatMargin(value: number | null | undefined): string {
  if (value == null) return "—";
  return `$${value.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })}`;
}

function pnlToneClass(value: number | null | undefined): string {
  if (value == null) return "trades-pnl--neutral";
  if (value > 0) return "trades-pnl--positive";
  if (value < 0) return "trades-pnl--negative";
  return "trades-pnl--neutral";
}

function EquitySparkline({ points }: { points: { equity: number }[] }) {
  if (points.length < 2) return null;
  const values = points.map((p) => p.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const w = 240;
  const h = 56;
  const pad = 2;
  const coords = values.map((v, i) => {
    const x = pad + (i / (values.length - 1)) * (w - pad * 2);
    const y = pad + (1 - (v - min) / span) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const end = values[values.length - 1] ?? 0;
  const start = values[0] ?? 0;
  const rising = end >= start;
  return (
    <svg
      className={`backtest-equity-spark${rising ? " backtest-equity-spark--up" : " backtest-equity-spark--down"}`}
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      role="img"
      aria-label="Equity curve sparkline"
    >
      <polyline fill="none" stroke="currentColor" strokeWidth="2" points={coords.join(" ")} />
    </svg>
  );
}

function formatParamLabel(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function actionKindClass(kind: string): string {
  const normalized = kind.trim().toLowerCase();
  if (normalized === "signal") return "backtest-action-kind--signal";
  if (normalized === "filter_fail") return "backtest-action-kind--filter";
  if (normalized === "entry" || normalized === "open") return "backtest-action-kind--entry";
  if (normalized === "exit" || normalized === "close") return "backtest-action-kind--exit";
  if (normalized === "sl" || normalized === "stop_loss") return "backtest-action-kind--sl";
  if (normalized === "tp" || normalized === "take_profit") return "backtest-action-kind--tp";
  return "backtest-action-kind--default";
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function ParamTree({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value == null) return <span className="settings-muted">—</span>;
  if (typeof value !== "object") {
    return <span className="backtest-param-leaf">{String(value)}</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="settings-muted">None</span>;
    }
    const allObjects = value.every(isPlainObject);
    return (
      <ul className={`backtest-param-list${allObjects ? " backtest-param-list--cards" : ""}`}>
        {value.map((item, index) => (
          <li
            key={index}
            className={allObjects ? "backtest-param-list-card" : undefined}
          >
            {allObjects ? (
              <p className="backtest-param-list-card-label">#{index + 1}</p>
            ) : null}
            <ParamTree value={item} depth={depth + 1} />
          </li>
        ))}
      </ul>
    );
  }
  const entries = Object.entries(value);
  if (entries.length === 0) {
    return <span className="settings-muted">No parameters</span>;
  }
  return (
    <dl
      className={`backtest-param-grid${depth > 0 ? " backtest-param-grid--nested" : " backtest-param-grid--root"}`}
    >
      {entries.map(([key, child]) => {
        const isSection = isPlainObject(child) || Array.isArray(child);
        return (
          <div
            key={key}
            className={`backtest-param-row${isSection ? " backtest-param-row--section" : " backtest-param-row--leaf"}`}
          >
            <dt>{formatParamLabel(key)}</dt>
            <dd>
              <ParamTree value={child} depth={depth + 1} />
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

export default function BacktestRunView() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const { formatInstant } = useGeneralSettings();
  const [run, setRun] = useState<BacktestRun | null>(null);
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [candles, setCandles] = useState<CandleBar[]>([]);
  const [candlesError, setCandlesError] = useState<string | null>(null);
  const [actions, setActions] = useState<BacktestAction[]>([]);
  const [logs, setLogs] = useState<BacktestLog[]>([]);
  const [tab, setTab] = useState<PanelTab>("overview");
  const [selectedActionIndex, setSelectedActionIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [candlesLoading, setCandlesLoading] = useState(true);
  const [logFollow, setLogFollow] = useState(true);
  const [logLevel, setLogLevel] = useState<string>("all");
  const [logsExpanded, setLogsExpanded] = useState(false);
  const [eventStepKind, setEventStepKind] = useState<EventStepKind>("action");
  const [feedbackSettings, setFeedbackSettings] = useState<BacktestSettings | null>(null);
  const [analyzeBusy, setAnalyzeBusy] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [selectedSuggestionIds, setSelectedSuggestionIds] = useState<Set<string>>(new Set());
  const selectedActionItemRef = useRef<HTMLButtonElement | null>(null);
  const feedbackMarkdownRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    setLoading(true);
    api
      .getBacktestRun(runId)
      .then((data) => {
        if (!cancelled) setRun(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load backtest");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  useEffect(() => {
    let cancelled = false;
    api
      .getBacktestSettings()
      .then((data) => {
        if (!cancelled) setFeedbackSettings(data);
      })
      .catch(() => {
        if (!cancelled) setFeedbackSettings(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const show =
      Boolean(feedbackSettings?.ai_feedback_enabled) || Boolean(run?.ai_feedback);
    if (tab === "feedback" && !show) {
      setTab("overview");
    }
  }, [tab, feedbackSettings?.ai_feedback_enabled, run?.ai_feedback]);

  useEffect(() => {
    if (!run?.strategy_id) {
      setStrategy(null);
      return;
    }
    let cancelled = false;
    api
      .getStrategy(run.strategy_id)
      .then((data) => {
        if (!cancelled) setStrategy(data);
      })
      .catch(() => {
        if (!cancelled) setStrategy(null);
      });
    return () => {
      cancelled = true;
    };
  }, [run?.strategy_id]);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    void api
      .listBacktestActions(runId, { limit: 5000 })
      .then((data) => {
        if (!cancelled) setActions(data.actions);
      })
      .catch(() => {
        if (!cancelled) setActions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [runId, run?.status]);

  useEffect(() => {
    if (!runId || !run) return;
    const status = normalizeBacktestRunStatus(run.status);
    if (status !== "running" && status !== "queued") return;

    let cancelled = false;
    const refreshActions = () => {
      void api.listBacktestActions(runId, { limit: 5000 }).then((data) => {
        if (!cancelled) setActions(data.actions);
      });
    };
    const poll = () => {
      void api.getBacktestRun(runId).then((data) => {
        if (!cancelled) setRun(data);
      });
      void api.listBacktestLogs(runId, { limit: 500 }).then((data) => {
        if (!cancelled) setLogs(data.logs);
      });
      refreshActions();
    };
    poll();
    const interval = window.setInterval(poll, 1500);

    let channel: { unsubscribe: () => void } | null = null;
    void getSupabaseBrowserClient().then((supabase) => {
      if (!supabase || cancelled) return;
      const sub = supabase
        .channel(`backtest-run:${runId}`)
        .on(
          "postgres_changes",
          { event: "UPDATE", schema: "brokerai", table: "backtest_runs", filter: `id=eq.${runId}` },
          () => poll(),
        )
        .on(
          "postgres_changes",
          {
            event: "INSERT",
            schema: "brokerai",
            table: "backtest_logs",
            filter: `run_id=eq.${runId}`,
          },
          () => {
            void api.listBacktestLogs(runId, { limit: 500 }).then((data) => {
              if (!cancelled) setLogs(data.logs);
            });
          },
        )
        .on(
          "postgres_changes",
          {
            event: "INSERT",
            schema: "brokerai",
            table: "backtest_actions",
            filter: `run_id=eq.${runId}`,
          },
          () => refreshActions(),
        )
        .subscribe();
      channel = {
        unsubscribe: () => {
          void supabase.removeChannel(sub);
        },
      };
    });

    return () => {
      cancelled = true;
      window.clearInterval(interval);
      channel?.unsubscribe();
    };
  }, [runId, run?.status]);

  useEffect(() => {
    if (!runId || !run) return;
    const feedbackStatus = run.ai_feedback?.status;
    if (feedbackStatus !== "queued" && feedbackStatus !== "running") return;

    let cancelled = false;
    const poll = () => {
      void api.getBacktestRun(runId).then((data) => {
        if (!cancelled) setRun(data);
      });
    };
    poll();
    const interval = window.setInterval(poll, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [runId, run?.ai_feedback?.status]);

  useEffect(() => {
    if (!runId || !run) return;
    const symbol = run.instrument || run.instruments[0];
    if (!symbol) {
      setCandles([]);
      setCandlesError("Backtest run has no instrument");
      setCandlesLoading(false);
      return;
    }
    let cancelled = false;
    setCandlesLoading(true);
    setCandlesError(null);
    api
      .getBacktestRunCandles(runId)
      .then((data) => {
        if (cancelled) return;
        setCandles(data.candles);
        if (data.candles.length === 0) {
          setCandlesError("No candle data for this backtest window.");
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setCandles([]);
        setCandlesError(err instanceof Error ? err.message : "Failed to load chart data");
      })
      .finally(() => {
        if (!cancelled) setCandlesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [runId, run?.id, run?.period_start, run?.period_end, run?.instrument, run?.timeframe]);

  const timeframe = (run?.timeframe || "M15") as Timeframe;
  const symbol = run?.instrument || run?.instruments[0] || null;
  const overlayItems = useMemo(
    () => (strategy ? decomposeStrategyToLayers(strategy) : []),
    [strategy],
  );
  const selectedAction = actions[selectedActionIndex] ?? null;

  useEffect(() => {
    selectedActionItemRef.current?.scrollIntoView({
      block: "nearest",
      behavior: "smooth",
    });
  }, [selectedActionIndex, tab]);

  const actionMarkers = useMemo(() => {
    const fills = backtestActionsToChartMarkers(actions);
    const selected = backtestActionToSelectedMarker(selectedAction);
    if (!selected || selected.role !== "skipped") return fills;
    if (fills.some((marker) => marker.sequence === selected.sequence)) return fills;
    return [...fills, selected];
  }, [actions, selectedAction]);

  const focusWindow = useMemo(() => {
    // Prefer the selected action (or period start) over current_bar so a completed
    // run does not zoom to the last bar before the user steps through.
    const anchor =
      selectedAction?.bar_time || run?.period_start || run?.current_bar;
    if (!anchor) return null;
    const date = parseAppInstant(anchor);
    if (!date) return null;
    const center = date.getTime();

    // Keep the full backtest period in the series so the user can pan/scroll
    // across the entire run. Zoom uses a fixed bar count for the timeframe.
    const periodStart = parseAppInstant(run?.period_start || "")?.getTime();
    const periodEnd = parseAppInstant(run?.period_end || "")?.getTime();
    const candleStart = candles.length
      ? parseAppInstant(candles[0]?.time || "")?.getTime()
      : null;
    const candleEnd = candles.length
      ? parseAppInstant(candles[candles.length - 1]?.time || "")?.getTime()
      : null;
    const displayFrom = periodStart ?? candleStart ?? center;
    const displayTo = periodEnd ?? candleEnd ?? center;
    if (displayFrom == null || displayTo == null) return null;

    return buildCenteredBarFocusWindow({
      anchorIso: anchor,
      timeframe,
      displaySinceMs: displayFrom,
      displayUntilMs: displayTo,
    });
  }, [
    selectedAction?.bar_time,
    run?.period_start,
    run?.period_end,
    run?.current_bar,
    candles,
    timeframe,
  ]);

  const filteredLogs = useMemo(() => {
    if (logLevel === "all") return logs;
    return logs.filter((log) => log.level === logLevel);
  }, [logs, logLevel]);

  const logText =
    filteredLogs.length === 0
      ? "No log lines yet."
      : filteredLogs.map((log) => `[${log.level}] ${log.message}`).join("\n");

  function handleLogScroll(event: UIEvent<HTMLPreElement>) {
    const el = event.currentTarget;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    if (!atBottom && logFollow) setLogFollow(false);
  }

  function bindLogFollowRef(el: HTMLPreElement | null) {
    if (el && logFollow) el.scrollTop = el.scrollHeight;
  }

  function stepEvent(kind: EventStepKind, direction: 1 | -1) {
    const index = findEventIndex(actions, selectedActionIndex, kind, direction);
    if (index < 0) return;
    setSelectedActionIndex(index);
    setTab("actions");
  }

  function stepTime(mode: TimeStepMode, direction: 1 | -1) {
    const anchor = selectedAction?.bar_time || run?.current_bar || run?.period_start;
    if (!anchor) return;
    const date = parseAppInstant(anchor);
    if (!date) return;
    const deltaMs =
      mode === "1d" ? 86_400_000 : mode === "7d" ? 7 * 86_400_000 : 30 * 86_400_000;
    const target = date.getTime() + deltaMs * direction;

    if (direction > 0) {
      let best = selectedActionIndex;
      for (let i = selectedActionIndex + 1; i < actions.length; i += 1) {
        const t = parseAppInstant(actions[i].bar_time || "");
        if (!t) continue;
        best = i;
        if (t.getTime() >= target) break;
      }
      setSelectedActionIndex(best);
    } else {
      let best = selectedActionIndex;
      for (let i = selectedActionIndex - 1; i >= 0; i -= 1) {
        const t = parseAppInstant(actions[i].bar_time || "");
        if (!t) continue;
        best = i;
        if (t.getTime() <= target) break;
      }
      setSelectedActionIndex(best);
    }
    setTab("actions");
  }

  async function startRun() {
    if (!runId) return;
    const updated = await api.startBacktestRun(runId);
    setRun(updated);
  }

  async function cancelRun() {
    if (!runId) return;
    const updated = await api.cancelBacktestRun(runId);
    setRun(updated);
  }

  async function requestAnalyze() {
    if (!runId) return;
    setAnalyzeBusy(true);
    setAnalyzeError(null);
    try {
      const updated = await api.requestBacktestAiFeedback(runId);
      setRun(updated);
      setTab("feedback");
    } catch (err) {
      setAnalyzeError(err instanceof Error ? err.message : "Failed to start AI feedback");
    } finally {
      setAnalyzeBusy(false);
    }
  }

  const feedbackStatus = run?.ai_feedback?.status ?? null;
  const feedbackFinishedAt = run?.ai_feedback?.finished_at ?? null;
  useEffect(() => {
    if (feedbackStatus !== "completed") return;
    const suggestions = (run?.ai_feedback?.suggestions ?? []) as AiFeedbackSuggestion[];
    setSelectedSuggestionIds(new Set(suggestions.map((s) => s.id)));
  }, [feedbackStatus, feedbackFinishedAt]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) {
    return <div className="center-page">Loading backtest…</div>;
  }
  if (error || !run) {
    return (
      <div className="analysis-run-view">
        <Link to={ROUTES.research.backtest} className="research-back-link">
          <ArrowLeft size={16} /> Backtests
        </Link>
        <p className="settings-error">{error || "Backtest not found"}</p>
      </div>
    );
  }

  const status = normalizeBacktestRunStatus(run.status);
  const params = run.params_snapshot || strategy?.params || {};
  const feedback = run.ai_feedback ?? null;
  const feedbackSuggestions = (feedback?.suggestions ?? []) as AiFeedbackSuggestion[];
  const feedbackRunning =
    feedback?.status === "queued" || feedback?.status === "running";

  function toggleSuggestion(id: string) {
    setSelectedSuggestionIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function openSuggestionsInBuilder() {
    if (!run?.params_snapshot || !run.strategy_id || !runId) return;
    const selected = feedbackSuggestions.filter((s) => selectedSuggestionIds.has(s.id));
    if (selected.length === 0) return;
    const patched = applySuggestionsToParams(
      run.params_snapshot as StrategyParamsV1,
      selected,
    );
    storeBacktestAiDraft({
      runId,
      strategyId: run.strategy_id,
      params: patched,
      appliedSuggestionIds: selected.map((s) => s.id),
      createdAt: new Date().toISOString(),
    });
    navigate(
      `${ROUTES.research.strategyEdit(run.strategy_id)}?fromBacktest=${encodeURIComponent(runId)}`,
    );
  }
  const feedbackFeatureEnabled = Boolean(feedbackSettings?.ai_feedback_enabled);
  const showFeedbackTab = feedbackFeatureEnabled || Boolean(feedback);
  const aiEnabled = Boolean(
    feedbackSettings?.ai_feedback_enabled &&
      feedbackSettings.ai_feedback_model_id &&
      feedbackSettings.ai_feedback_model_name,
  );
  const analyzeDisabled = analyzeBusy || feedbackRunning || !aiEnabled;
  const analyzeTitle = !aiEnabled
    ? "Enable AI feedback and select a model in Settings → Backtesting"
    : feedbackRunning
      ? "Analysis in progress"
      : "Analyze this backtest with AI";
  const panelTabs: PanelTab[] = showFeedbackTab
    ? ["overview", "strategy", "actions", "feedback"]
    : ["overview", "strategy", "actions"];

  async function exportFeedbackPdf() {
    if (!feedback?.markdown || !feedbackMarkdownRef.current) return;
    setExportError(null);
    try {
      const metaLines: string[] = [];
      if (feedback.model_name) metaLines.push(feedback.model_name);
      if (feedback.finished_at) metaLines.push(formatInstant(feedback.finished_at));
      const title = `${run.name || run.strategy_name} — AI feedback`;
      await downloadBacktestFeedbackPdf({
        title,
        filename: `${run.name || run.strategy_name}-ai-feedback`,
        subtitle: [
          run.strategy_name,
          symbol,
          TIMEFRAME_LABELS[timeframe] ?? timeframe,
          run.period,
        ]
          .filter(Boolean)
          .join(" · "),
        metaLines,
        bodyHtml: feedbackMarkdownRef.current.innerHTML,
      });
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Failed to export PDF");
    }
  }

  return (
    <div className="analysis-run-view backtest-run-view">
      <header className="analysis-run-view-header">
        <Link to={ROUTES.research.backtest} className="research-back-link">
          <ArrowLeft size={16} strokeWidth={1.75} />
          Backtests
        </Link>
        <div className="analysis-run-view-title-row">
          <div className="analysis-run-view-title-block">
            <h1 className="page-title analysis-run-view-title">
              {run.name || run.strategy_name}
            </h1>
            <p className="settings-muted analysis-run-view-subtitle">
              {run.strategy_name}
              {symbol ? ` · ${symbol}` : ""}
              {` · ${TIMEFRAME_LABELS[timeframe] ?? timeframe}`}
              {` · ${backtestRunStatusLabel(status)}`}
              {run.period ? ` · ${run.period}` : ""}
            </p>
          </div>
          <div className="analysis-run-view-actions">
            {status === "queued" ? (
              <button type="button" className="btn btn-sm" onClick={() => void startRun()}>
                Start
              </button>
            ) : null}
            {status === "queued" || status === "running" ? (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => void cancelRun()}
              >
                Cancel
              </button>
            ) : null}
            {status === "completed" ? (
              <button
                type="button"
                className="btn btn-sm"
                disabled={analyzeDisabled}
                title={analyzeTitle}
                onClick={() => void requestAnalyze()}
              >
                {feedbackRunning || analyzeBusy ? "Analyzing…" : "Analyze with AI"}
              </button>
            ) : null}
          </div>
        </div>
        {status === "running" || status === "queued" ? (
          <div className="backtest-progress">
            <div className="backtest-progress-bar" aria-hidden>
              <div
                className="backtest-progress-bar-fill"
                style={{ width: `${Math.max(0, Math.min(100, run.progress_pct ?? 0))}%` }}
              />
            </div>
            <p className="settings-muted">
              {Math.round(run.progress_pct ?? 0)}%
              {run.status_message ? ` · ${run.status_message}` : ""}
            </p>
          </div>
        ) : null}
      </header>

      {status === "completed" ? (
        <div className="backtest-step-controls" aria-label="Step through backtest">
          <span className="backtest-step-controls-label">Step through</span>

          <div className="backtest-step-group" role="group" aria-label="Time jumps">
            {(["1d", "7d", "1m"] as const).map((mode) => (
              <div key={mode} className="backtest-step-time-pair">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm backtest-step-time-btn"
                  onClick={() => stepTime(mode, -1)}
                  disabled={actions.length === 0 || selectedActionIndex <= 0}
                  aria-label={`Back ${mode}`}
                  title={`Back ${mode}`}
                >
                  <ChevronLeft className="backtest-step-icon" size={15} strokeWidth={2.25} aria-hidden />
                  <span>{mode}</span>
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm backtest-step-time-btn"
                  onClick={() => stepTime(mode, 1)}
                  disabled={
                    actions.length === 0 || selectedActionIndex >= actions.length - 1
                  }
                  aria-label={`Forward ${mode}`}
                  title={`Forward ${mode}`}
                >
                  <span>{mode}</span>
                  <ChevronRight className="backtest-step-icon" size={15} strokeWidth={2.25} aria-hidden />
                </button>
              </div>
            ))}
          </div>

          <div className="backtest-step-group backtest-step-group--events" role="group" aria-label="Event jumps">
            <EventStepMenu
              direction="previous"
              kind={eventStepKind}
              disabled={actions.length === 0 || selectedActionIndex <= 0}
              onKindChange={setEventStepKind}
              onStep={(kind) => stepEvent(kind, -1)}
            />
            <EventStepMenu
              direction="next"
              kind={eventStepKind}
              disabled={actions.length === 0 || selectedActionIndex >= actions.length - 1}
              onKindChange={setEventStepKind}
              onStep={(kind) => stepEvent(kind, 1)}
            />
          </div>
        </div>
      ) : null}

      <div className="analysis-run-detail-layout analysis-run-detail-layout--ready">
        <div className="analysis-run-chart-col">
          <ExploreCandleChart
            symbol={symbol}
            timeframe={timeframe}
            candles={candles}
            loading={candlesLoading}
            error={candlesError}
            overlayItems={overlayItems}
            focusWindow={focusWindow}
            actionMarkers={actionMarkers}
            selectedActionSequence={selectedAction?.sequence ?? null}
          />
          {(status === "running" || logs.length > 0) && (
            <div className="backtest-log-viewer">
              <div className="backtest-log-viewer-header">
                <strong>Logs</strong>
                <select
                  className="research-select"
                  value={logLevel}
                  onChange={(e) => setLogLevel(e.target.value)}
                  aria-label="Log level filter"
                >
                  <option value="all">All levels</option>
                  <option value="DEBUG">DEBUG</option>
                  <option value="INFO">INFO</option>
                  <option value="WARNING">WARNING</option>
                  <option value="ERROR">ERROR</option>
                </select>
                <div className="backtest-log-viewer-header-actions">
                  <label className="backtest-log-follow">
                    <input
                      type="checkbox"
                      checked={logFollow}
                      onChange={(e) => setLogFollow(e.target.checked)}
                    />
                    Follow
                  </label>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setLogsExpanded(true)}
                    aria-label="Expand logs"
                  >
                    <Maximize2 size={14} aria-hidden="true" />
                    Expand
                  </button>
                </div>
              </div>
              <pre
                className="backtest-log-viewer-body"
                onScroll={handleLogScroll}
                ref={bindLogFollowRef}
              >
                {logText}
              </pre>
            </div>
          )}
        </div>

        <aside className="analysis-run-panel-col backtest-panel-col">
          <div
            className={`backtest-panel-tabs research-signals-tabs${
              showFeedbackTab ? " backtest-panel-tabs--with-feedback" : ""
            }`}
            role="tablist"
          >
            {panelTabs.map((id) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                className={`research-signals-tab${tab === id ? " research-signals-tab--active" : ""}`}
                onClick={() => setTab(id)}
              >
                {id === "overview"
                  ? "Overview"
                  : id === "strategy"
                    ? "Strategy"
                    : id === "actions"
                      ? "Actions"
                      : "Feedback"}
              </button>
            ))}
          </div>

          {tab === "overview" ? (
            <div className="backtest-panel-body">
              <section className="backtest-overview-hero" aria-label="Realized PnL">
                <p className="backtest-overview-hero-label">Realized PnL</p>
                <p className={`backtest-overview-hero-value ${pnlToneClass(run.stats.realized_pnl)}`}>
                  {formatPnl(run.stats.realized_pnl)}
                </p>
                <p className="backtest-overview-hero-meta settings-muted">
                  {backtestRunStatusLabel(status)}
                  {run.period ? ` · ${run.period}` : ""}
                  {symbol ? ` · ${symbol}` : ""}
                </p>
              </section>

              <div className="backtest-overview-metrics" role="list">
                <div className="backtest-overview-metric" role="listitem">
                  <span className="backtest-overview-metric-label">Account margin</span>
                  <span className="backtest-overview-metric-value">
                    {formatMargin(run.account_margin ?? 10_000)}
                  </span>
                </div>
                <div className="backtest-overview-metric" role="listitem">
                  <span className="backtest-overview-metric-label">Trades</span>
                  <span className="backtest-overview-metric-value">
                    {run.stats.total_trades ?? "—"}
                  </span>
                </div>
                <div className="backtest-overview-metric" role="listitem">
                  <span className="backtest-overview-metric-label">Win rate</span>
                  <span className="backtest-overview-metric-value">
                    {formatWinRate(run.stats.win_rate)}
                  </span>
                </div>
                <div className="backtest-overview-metric" role="listitem">
                  <span className="backtest-overview-metric-label">Max drawdown</span>
                  <span className="backtest-overview-metric-value backtest-overview-metric-value--drawdown">
                    {formatDrawdown(run.stats.max_drawdown)}
                  </span>
                </div>
              </div>

              {(run.equity_curve?.length ?? 0) > 0 ? (
                <section className="backtest-equity-summary" aria-labelledby="backtest-equity-heading">
                  <div className="backtest-equity-summary-header">
                    <h3 className="trade-detail-section-title" id="backtest-equity-heading">
                      Equity
                    </h3>
                    <p className="settings-muted backtest-equity-summary-meta">
                      {run.equity_curve!.length} pts
                    </p>
                  </div>
                  <EquitySparkline points={run.equity_curve!} />
                  <dl className="backtest-equity-endpoints">
                    <div>
                      <dt>Start</dt>
                      <dd className={pnlToneClass(run.equity_curve![0]?.equity)}>
                        {formatPnl(run.equity_curve![0]?.equity)}
                      </dd>
                    </div>
                    <div>
                      <dt>End</dt>
                      <dd
                        className={pnlToneClass(
                          run.equity_curve![run.equity_curve!.length - 1]?.equity,
                        )}
                      >
                        {formatPnl(run.equity_curve![run.equity_curve!.length - 1]?.equity)}
                      </dd>
                    </div>
                  </dl>
                </section>
              ) : null}

              <section className="backtest-overview-meta" aria-labelledby="backtest-run-meta-heading">
                <h3 className="trade-detail-section-title" id="backtest-run-meta-heading">
                  Run
                </h3>
                <dl className="analysis-detail-list analysis-detail-list--compact">
                  <div className="analysis-detail-row">
                    <dt className="analysis-detail-label">Created</dt>
                    <dd className="analysis-detail-value">
                      {run.created_at ? formatInstant(run.created_at) : "—"}
                    </dd>
                  </div>
                  <div className="analysis-detail-row">
                    <dt className="analysis-detail-label">Started</dt>
                    <dd className="analysis-detail-value">
                      {run.started_at ? formatInstant(run.started_at) : "—"}
                    </dd>
                  </div>
                  <div className="analysis-detail-row">
                    <dt className="analysis-detail-label">Finished</dt>
                    <dd className="analysis-detail-value">
                      {run.finished_at ? formatInstant(run.finished_at) : "—"}
                    </dd>
                  </div>
                  {run.period_start || run.period_end ? (
                    <div className="analysis-detail-row">
                      <dt className="analysis-detail-label">Period</dt>
                      <dd className="analysis-detail-value">
                        {run.period_start ? formatInstant(run.period_start) : "—"}
                        {" → "}
                        {run.period_end ? formatInstant(run.period_end) : "—"}
                      </dd>
                    </div>
                  ) : null}
                </dl>
              </section>

              {run.error ? <p className="settings-error backtest-overview-error">{run.error}</p> : null}
            </div>
          ) : null}

          {tab === "strategy" ? (
            <div className="backtest-panel-body">
              <section className="backtest-strategy-hero" aria-label="Strategy summary">
                <p className="backtest-overview-hero-label">Strategy snapshot</p>
                <p className="backtest-strategy-hero-name">{run.strategy_name}</p>
                <p className="backtest-overview-hero-meta settings-muted">
                  Read-only parameters used for this run
                  {symbol ? ` · ${symbol}` : ""}
                  {` · ${TIMEFRAME_LABELS[timeframe] ?? timeframe}`}
                </p>
              </section>

              <section className="backtest-strategy-params" aria-labelledby="backtest-params-heading">
                <h3 className="trade-detail-section-title" id="backtest-params-heading">
                  Parameters
                </h3>
                <ParamTree value={params} />
              </section>
            </div>
          ) : null}

          {tab === "actions" ? (
            <div className="backtest-panel-body backtest-actions-panel">
              <section className="backtest-actions-hero" aria-label="Actions summary">
                <div className="backtest-actions-hero-main">
                  <p className="backtest-overview-hero-label">Actions</p>
                  <p className="backtest-actions-hero-count">
                    {actions.length === 0 ? "None yet" : `${actions.length} recorded`}
                  </p>
                  <p className="settings-muted backtest-actions-order-hint">
                    Oldest → newest
                  </p>
                </div>
                {actions.length > 0 ? (
                  <p className="settings-muted backtest-actions-hero-position">
                    {selectedActionIndex + 1} of {actions.length}
                  </p>
                ) : null}
              </section>

              {actions.length === 0 ? (
                <div className="backtest-actions-empty">
                  <p className="settings-muted">
                    No actions recorded yet. Step through once the run starts producing signals.
                  </p>
                </div>
              ) : (
                <ul className="backtest-actions-list">
                  {actions.map((action, index) => (
                    <li key={action.id}>
                      <button
                        type="button"
                        ref={index === selectedActionIndex ? selectedActionItemRef : undefined}
                        className={`backtest-action-item${
                          index === selectedActionIndex ? " backtest-action-item--active" : ""
                        }`}
                        onClick={() => setSelectedActionIndex(index)}
                      >
                        <span className="backtest-action-item-top">
                          <span
                            className={`backtest-action-kind ${actionKindClass(action.kind)}`}
                          >
                            {action.kind.replace(/_/g, " ")}
                          </span>
                          {action.bar_time ? (
                            <span className="backtest-action-time settings-muted">
                              {formatInstant(action.bar_time)}
                            </span>
                          ) : null}
                        </span>
                        <span className="backtest-action-message">{action.message}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}

          {tab === "feedback" ? (
            <div className="backtest-panel-body backtest-feedback-panel">
              <section className="backtest-actions-hero" aria-label="AI feedback">
                <div className="backtest-actions-hero-main">
                  <p className="backtest-overview-hero-label">AI feedback</p>
                  <p className="backtest-actions-hero-count">
                    {!feedback
                      ? "Not analyzed"
                      : feedback.status === "completed"
                        ? "Ready"
                        : feedback.status === "failed"
                          ? "Failed"
                          : "Analyzing…"}
                  </p>
                  {feedback?.model_name ? (
                    <p className="settings-muted backtest-actions-order-hint">
                      {feedback.model_name}
                      {feedback.finished_at
                        ? ` · ${formatInstant(feedback.finished_at)}`
                        : ""}
                    </p>
                  ) : null}
                </div>
                {status === "completed" ? (
                  <div className="backtest-feedback-hero-actions">
                    {feedback?.status === "completed" && feedback.markdown ? (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        title="Download feedback as PDF"
                        aria-label="Download AI feedback as PDF"
                        onClick={() => void exportFeedbackPdf()}
                      >
                        <FileDown size={14} strokeWidth={2} aria-hidden />
                        Download PDF
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="btn btn-sm"
                      disabled={analyzeDisabled}
                      title={analyzeTitle}
                      onClick={() => void requestAnalyze()}
                    >
                      {feedbackRunning || analyzeBusy
                        ? "Analyzing…"
                        : feedback?.status === "completed" || feedback?.status === "failed"
                          ? "Re-analyze"
                          : "Analyze"}
                    </button>
                  </div>
                ) : null}
              </section>

              {analyzeError ? <p className="settings-error">{analyzeError}</p> : null}
              {exportError ? <p className="settings-error">{exportError}</p> : null}

              {!feedback && !feedbackRunning ? (
                <div className="backtest-actions-empty">
                  <p className="settings-muted">
                    {aiEnabled
                      ? "Run Analyze with AI to get strategy improvement suggestions from your configured model."
                      : "Enable AI feedback and select a model in Settings → Backtesting to analyze this run."}
                  </p>
                  {!aiEnabled ? (
                    <p className="settings-muted">
                      <Link to="/settings/backtesting">Open Backtesting settings</Link>
                    </p>
                  ) : null}
                </div>
              ) : null}

              {feedbackRunning ? (
                <div className="backtest-actions-empty">
                  <p className="settings-muted">
                    Packaging results and waiting for the model… This can take a minute.
                  </p>
                </div>
              ) : null}

              {feedback?.status === "failed" ? (
                <div className="backtest-actions-empty">
                  <p className="settings-error">{feedback.error || "Analysis failed"}</p>
                </div>
              ) : null}

              {feedback?.status === "completed" && feedback.markdown ? (
                <div
                  className="research-report-body backtest-feedback-markdown"
                  ref={feedbackMarkdownRef}
                >
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {feedback.markdown}
                  </ReactMarkdown>
                </div>
              ) : null}

              {feedback?.status === "completed" && feedbackSuggestions.length > 0 ? (
                <section className="backtest-feedback-suggestions" aria-label="Structured suggestions">
                  <div className="backtest-feedback-suggestions-header">
                    <h3 className="backtest-feedback-suggestions-title">Builder suggestions</h3>
                    <p className="settings-muted">
                      Select changes to review in the strategy builder. Nothing is saved until you
                      confirm there.
                    </p>
                  </div>
                  <ul className="backtest-feedback-suggestion-list">
                    {feedbackSuggestions.map((suggestion) => (
                      <li key={suggestion.id} className="backtest-feedback-suggestion-card">
                        <label className="backtest-feedback-suggestion-label">
                          <input
                            type="checkbox"
                            checked={selectedSuggestionIds.has(suggestion.id)}
                            onChange={() => toggleSuggestion(suggestion.id)}
                          />
                          <span>
                            <strong>{suggestion.label || suggestion.path}</strong>
                            <span className="settings-muted">
                              {" "}
                              {suggestionDisplayValue(suggestion.from)} →{" "}
                              {suggestionDisplayValue(suggestion.to)}
                            </span>
                          </span>
                        </label>
                        {suggestion.rationale ? (
                          <p className="param-helper">{suggestion.rationale}</p>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={selectedSuggestionIds.size === 0 || !run.params_snapshot}
                    onClick={openSuggestionsInBuilder}
                  >
                    Open selected in builder
                  </button>
                </section>
              ) : null}
            </div>
          ) : null}
        </aside>
      </div>

      {logsExpanded ? (
        <StrategyOverlay
          onClose={() => setLogsExpanded(false)}
          titleId="backtest-logs-expanded-title"
          dialogClassName="model-overlay-dialog--backtest-logs"
        >
          <div className="model-overlay-body">
            <h4 className="model-overlay-title" id="backtest-logs-expanded-title">
              Logs
            </h4>
            <div className="backtest-log-viewer">
              <div className="backtest-log-viewer-header">
                <select
                  className="research-select"
                  value={logLevel}
                  onChange={(e) => setLogLevel(e.target.value)}
                  aria-label="Log level filter"
                >
                  <option value="all">All levels</option>
                  <option value="DEBUG">DEBUG</option>
                  <option value="INFO">INFO</option>
                  <option value="WARNING">WARNING</option>
                  <option value="ERROR">ERROR</option>
                </select>
                <div className="backtest-log-viewer-header-actions">
                  <label className="backtest-log-follow">
                    <input
                      type="checkbox"
                      checked={logFollow}
                      onChange={(e) => setLogFollow(e.target.checked)}
                    />
                    Follow
                  </label>
                </div>
              </div>
              <pre
                className="backtest-log-viewer-body backtest-log-viewer-body--expanded"
                onScroll={handleLogScroll}
                ref={bindLogFollowRef}
              >
                {logText}
              </pre>
            </div>
          </div>
          <div className="model-overlay-footer">
            <div className="confirm-actions model-overlay-actions">
              <div className="model-overlay-actions-primary">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setLogsExpanded(false)}
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </StrategyOverlay>
      ) : null}
    </div>
  );
}
