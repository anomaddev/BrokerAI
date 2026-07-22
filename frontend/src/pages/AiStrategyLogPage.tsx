import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Pencil,
  RefreshCw,
  Square,
} from "lucide-react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import {
  api,
  type AiStrategyActivityEvent,
  type AiStrategyActivityResponse,
  type AiStrategyStartupJob,
  type Strategy,
} from "../api/client";
import { useGeneralSettings } from "../hooks/useGeneralSettings";
import {
  activityKindLabel,
  activityStatusClass,
  executionPhaseLabel,
  startupStatusLabel,
  startupSteps,
  warmupProgressLabel,
} from "../lib/aiStrategy/activityLabels";
import { ROUTES } from "../lib/routes";
import { instrumentSelectionSummary } from "./strategies/strategyAssignment";

const IDLE_POLL_MS = 15_000;
const ACTIVE_POLL_MS = 3_000;
const DETAIL_PREVIEW_CHARS = 96;
const MEMORY_RULES_PREVIEW = 3;

/** Match ISO timestamps embedded in status strings (e.g. candle bar times). */
const ISO_IN_TEXT =
  /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?/g;

function isOpenStartupStatus(status: string | undefined): boolean {
  return status === "queued" || status === "running";
}

function canRetryStartup(status: string | undefined): boolean {
  return status === "failed" || status === "cancelled";
}

function instrumentLabel(strategy: Strategy): string {
  const summary = instrumentSelectionSummary(strategy.instrument_selection);
  if (summary) return summary;
  if (strategy.instruments?.length) return strategy.instruments.join(", ");
  return "—";
}

function humanizeStatusMessage(
  message: string,
  formatInstant: (value: string | null | undefined, style?: "short") => string,
): string {
  return message.replace(ISO_IN_TEXT, (match) => {
    const formatted = formatInstant(match, "short");
    return formatted && formatted !== "—" ? formatted : match;
  });
}

export default function AiStrategyLogPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { formatInstant } = useGeneralSettings();
  const [payload, setPayload] = useState<AiStrategyActivityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [promoting, setPromoting] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [cancelConfirmOpen, setCancelConfirmOpen] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const data = await api.getStrategyActivity(id, { limit: 80 });
      setPayload(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load AI Strategy log");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    async function firstLoad() {
      if (cancelled || !id) return;
      await load();
    }

    void firstLoad();
    return () => {
      cancelled = true;
    };
  }, [id, load]);

  useEffect(() => {
    if (!id || !payload) return;
    const intervalMs = payload.active ? ACTIVE_POLL_MS : IDLE_POLL_MS;
    const timer = window.setInterval(() => {
      void load();
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [id, payload?.active, load]);

  async function handlePromote() {
    if (!payload?.strategy || promoting) return;
    setPromoting(true);
    setActionError(null);
    try {
      await api.promoteStrategy(payload.strategy.id);
      await load();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not promote strategy");
    } finally {
      setPromoting(false);
    }
  }

  async function handleRetryStartup() {
    if (!payload?.strategy || retrying) return;
    setRetrying(true);
    setActionError(null);
    try {
      await api.retryStrategyStartup(payload.strategy.id);
      await load();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not retry startup");
    } finally {
      setRetrying(false);
    }
  }

  async function handleCancelStartup() {
    if (!payload?.strategy || cancelling) return;
    setCancelling(true);
    setActionError(null);
    setCancelConfirmOpen(false);
    try {
      await api.cancelStrategyStartup(payload.strategy.id);
      await load();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not cancel startup");
    } finally {
      setCancelling(false);
    }
  }

  if (!id) {
    return <Navigate to={ROUTES.research.aiStrategies} replace />;
  }

  if (loading && !payload) {
    return <div className="center-page">Loading AI Strategy log…</div>;
  }

  if (error && !payload) {
    return (
      <div>
        <div className="strategy-list-header">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => navigate(ROUTES.research.aiStrategies)}
          >
            <ArrowLeft size={16} strokeWidth={1.75} aria-hidden />
            AI Strategies
          </button>
        </div>
        <p className="settings-error">{error}</p>
      </div>
    );
  }

  if (!payload) {
    return <Navigate to={ROUTES.research.aiStrategies} replace />;
  }

  const strategy = payload.strategy;
  if (strategy.preset_id !== "ai_strategy") {
    return <Navigate to={ROUTES.research.strategyEdit(strategy.id)} replace />;
  }

  const startup = payload.startup_job;
  const digest = payload.latest_digest;
  const warmup = warmupProgressLabel(strategy);

  return (
    <div className="ai-strategy-log">
      <header className="ai-strategy-log-hero">
        <div className="ai-strategy-log-hero-top">
          <button
            type="button"
            className="btn btn-secondary ai-strategy-log-back"
            onClick={() => navigate(ROUTES.research.aiStrategies)}
          >
            <ArrowLeft size={16} strokeWidth={1.75} aria-hidden />
            AI Strategies
          </button>
          <div className="ai-strategy-log-actions">
            {strategy.execution_phase === "ready" ? (
              <button
                type="button"
                className="btn"
                disabled={promoting}
                onClick={() => void handlePromote()}
              >
                {promoting ? "Promoting…" : "Promote to live"}
              </button>
            ) : null}
            {isOpenStartupStatus(startup?.status) ? (
              <button
                type="button"
                className="btn btn-danger"
                disabled={cancelling}
                onClick={() => setCancelConfirmOpen(true)}
              >
                <Square size={16} strokeWidth={1.75} aria-hidden />
                {cancelling ? "Cancelling…" : "Cancel startup"}
              </button>
            ) : null}
            {canRetryStartup(startup?.status) ? (
              <button
                type="button"
                className="btn btn-secondary"
                disabled={retrying}
                onClick={() => void handleRetryStartup()}
              >
                <RefreshCw size={16} strokeWidth={1.75} aria-hidden />
                {retrying ? "Restarting…" : "Restart startup"}
              </button>
            ) : null}
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => navigate(ROUTES.research.strategyEdit(strategy.id))}
            >
              <Pencil size={16} strokeWidth={1.75} aria-hidden />
              Edit parameters
            </button>
          </div>
        </div>
        <h1 className="page-title ai-strategy-log-title">{strategy.name}</h1>
        <p className="ai-strategy-log-meta">
          <span>{instrumentLabel(strategy)}</span>
          <span className="ai-strategy-log-meta-sep" aria-hidden>
            ·
          </span>
          <span>{strategy.enabled ? "Enabled" : "Disabled"}</span>
          {strategy.execution_phase ? (
            <>
              <span className="ai-strategy-log-meta-sep" aria-hidden>
                ·
              </span>
              <span>
                {executionPhaseLabel(strategy.execution_phase)}
                {warmup ? ` ${warmup}` : ""}
              </span>
            </>
          ) : null}
          {payload.active ? (
            <>
              <span className="ai-strategy-log-meta-sep" aria-hidden>
                ·
              </span>
              <span className="ai-strategy-log-live">Live updating</span>
            </>
          ) : null}
        </p>
        {strategy.description ? (
          <p className="settings-muted ai-strategy-log-subtitle">{strategy.description}</p>
        ) : null}
      </header>

      {cancelConfirmOpen ? (
        <div
          className="confirm-overlay"
          role="presentation"
          onClick={() => !cancelling && setCancelConfirmOpen(false)}
        >
          <div
            className="confirm-dialog"
            role="alertdialog"
            aria-labelledby="cancel-startup-title"
            aria-describedby="cancel-startup-message"
            onClick={(event) => event.stopPropagation()}
          >
            <h4 id="cancel-startup-title">Cancel AI Strategy startup?</h4>
            <p id="cancel-startup-message">
              This stops the current startup pipeline and any in-flight startup
              backtest. The strategy, memory digests, and warm-up progress are kept.
              You can restart startup afterward.
            </p>
            <div className="confirm-actions">
              <button
                type="button"
                className="btn btn-secondary"
                disabled={cancelling}
                onClick={() => setCancelConfirmOpen(false)}
              >
                Keep running
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={cancelling}
                onClick={() => void handleCancelStartup()}
              >
                {cancelling ? "Cancelling…" : "Cancel startup"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {actionError ? <p className="settings-error">{actionError}</p> : null}
      {error ? <p className="settings-error">{error}</p> : null}

      <StartupProgress
        job={startup}
        formatInstant={formatInstant}
        onOpenBacktest={(runId) => navigate(ROUTES.research.backtestRun(runId))}
      />

      <section className="ai-strategy-log-panel ai-strategy-log-activity">
        <div className="ai-strategy-log-panel-header">
          <h2 className="ai-strategy-log-panel-title">Activity</h2>
        </div>
        {payload.events.length === 0 ? (
          <p className="settings-muted">No activity recorded yet.</p>
        ) : (
          <ul className="ai-strategy-log-feed">
            {payload.events.map((event) => (
              <ActivityRow
                key={event.id}
                event={event}
                formatInstant={formatInstant}
              />
            ))}
          </ul>
        )}
      </section>

      <DigestCard digest={digest} formatInstant={formatInstant} />
    </div>
  );
}

function shortDetail(raw: string | null | undefined): { text: string; full: string } {
  const full = (raw || "").trim();
  if (!full) return { text: "—", full: "" };
  if (full.length <= DETAIL_PREVIEW_CHARS) return { text: full, full };
  return { text: `${full.slice(0, DETAIL_PREVIEW_CHARS - 1)}…`, full };
}

function ActivityRow({
  event,
  formatInstant,
}: {
  event: AiStrategyActivityEvent;
  formatInstant: (value: string | null | undefined, style?: "short") => string;
}) {
  const metaMessage =
    typeof event.meta?.status_message === "string" ? event.meta.status_message : null;
  const rawDetail = metaMessage || event.detail;
  const { text, full } = shortDetail(
    rawDetail ? humanizeStatusMessage(rawDetail, formatInstant) : rawDetail,
  );
  const title = event.href ? (
    <Link to={event.href} className="ai-strategy-log-link">
      {event.title}
    </Link>
  ) : (
    event.title
  );

  return (
    <li className={`ai-strategy-log-feed-row ${activityStatusClass(event.status)}`}>
      <time className="ai-strategy-log-feed-time" dateTime={event.occurred_at}>
        {formatInstant(event.occurred_at, "short")}
      </time>
      <div className="ai-strategy-log-feed-body">
        <div className="ai-strategy-log-feed-headline">
          <span className={`research-tag ai-strategy-log-kind ai-strategy-log-kind--${event.kind}`}>
            {activityKindLabel(event.kind)}
          </span>
          <span className="ai-strategy-log-feed-title">{title}</span>
        </div>
        <p className="ai-strategy-log-feed-detail" title={full || undefined}>
          {text}
        </p>
      </div>
    </li>
  );
}

function StartupProgress({
  job,
  formatInstant,
  onOpenBacktest,
}: {
  job: AiStrategyStartupJob | null;
  formatInstant: (value: string | null | undefined, style?: "short") => string;
  onOpenBacktest: (runId: string) => void;
}) {
  if (!job) {
    return (
      <section className="ai-strategy-log-panel ai-strategy-log-startup">
        <h2 className="ai-strategy-log-panel-title">Startup</h2>
        <p className="settings-muted">No create-time startup job for this strategy.</p>
      </section>
    );
  }

  const steps = startupSteps(job);
  const rawStatus = (job.status_message || "").trim() || startupStatusLabel(job);
  const statusMessage = humanizeStatusMessage(rawStatus, formatInstant);
  const open = job.status === "queued" || job.status === "running";

  return (
    <section className="ai-strategy-log-panel ai-strategy-log-startup">
      <div className="ai-strategy-log-startup-head">
        <div>
          <h2 className="ai-strategy-log-panel-title">Startup</h2>
          <p
            className={
              job.status === "failed" ? "settings-error" : "ai-strategy-log-status-message"
            }
          >
            {job.status === "failed"
              ? humanizeStatusMessage(job.error || statusMessage, formatInstant)
              : statusMessage}
          </p>
        </div>
        <div className="ai-strategy-log-startup-actions">
          {job.current_backtest_run_id ? (
            <button
              type="button"
              className="btn btn-sm btn-secondary"
              onClick={() => onOpenBacktest(job.current_backtest_run_id!)}
            >
              <ExternalLink size={14} strokeWidth={1.75} aria-hidden />
              Open signal review
            </button>
          ) : null}
        </div>
      </div>
      <ol className="ai-strategy-log-steps ai-strategy-log-steps--row">
        {steps.map((step) => (
          <li
            key={step.id}
            className={`ai-strategy-log-step ai-strategy-log-step--${step.state}`}
          >
            <span className="ai-strategy-log-step-marker" aria-hidden />
            <div className="ai-strategy-log-step-copy">
              <span className="ai-strategy-log-step-label">{step.label}</span>
              <span className="ai-strategy-log-step-detail">{step.detail}</span>
            </div>
          </li>
        ))}
      </ol>
      {open ? (
        <p className="settings-muted ai-strategy-log-live-hint">Updates every few seconds</p>
      ) : null}
    </section>
  );
}

function DigestCard({
  digest,
  formatInstant,
}: {
  digest: AiStrategyActivityResponse["latest_digest"];
  formatInstant: (value: string | null | undefined, style?: "short") => string;
}) {
  const [expanded, setExpanded] = useState(false);
  const rules = digest?.standing_rules ?? [];
  const visibleRules = expanded ? rules : rules.slice(0, MEMORY_RULES_PREVIEW);
  const hiddenCount = Math.max(0, rules.length - MEMORY_RULES_PREVIEW);

  return (
    <section className="ai-strategy-log-panel ai-strategy-log-memory">
      <div className="ai-strategy-log-panel-header ai-strategy-log-memory-head">
        <h2 className="ai-strategy-log-panel-title">Memory</h2>
        {digest ? (
          <p className="ai-strategy-log-memory-meta">
            v{digest.version ?? "—"}
            {digest.created_at ? ` · ${formatInstant(digest.created_at, "short")}` : ""}
            {digest.standing_rule_count != null || digest.anti_rule_count != null
              ? ` · ${digest.standing_rule_count ?? 0} standing · ${digest.anti_rule_count ?? 0} anti`
              : ""}
          </p>
        ) : null}
      </div>
      {!digest ? (
        <p className="settings-muted">No memory digest yet.</p>
      ) : (
        <>
          {digest.summary ? (
            <p className="ai-strategy-log-digest-summary">{digest.summary}</p>
          ) : null}
          {rules.length > 0 ? (
            <>
              <ul className="ai-strategy-log-rules">
                {visibleRules.map((rule) => (
                  <li key={rule}>{rule}</li>
                ))}
              </ul>
              {hiddenCount > 0 ? (
                <button
                  type="button"
                  className="btn btn-sm btn-secondary ai-strategy-log-rules-toggle"
                  onClick={() => setExpanded((value) => !value)}
                >
                  {expanded ? (
                    <>
                      <ChevronUp size={14} strokeWidth={1.75} aria-hidden />
                      Show fewer
                    </>
                  ) : (
                    <>
                      <ChevronDown size={14} strokeWidth={1.75} aria-hidden />
                      Show {hiddenCount} more
                    </>
                  )}
                </button>
              ) : null}
            </>
          ) : null}
        </>
      )}
    </section>
  );
}
