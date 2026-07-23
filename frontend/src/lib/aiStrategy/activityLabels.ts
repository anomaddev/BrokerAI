import type {
  AiStrategyActivityEvent,
  AiStrategyStartupJob,
  Strategy,
  StrategyExecutionPhase,
} from "../../api/client";

const REPORT_LABELS: Record<string, string> = {
  daily_report: "Daily report",
  weekly_brief: "Weekly brief",
  weekly_debrief: "Weekly debrief",
};

export function humanReportLabel(kind: string): string {
  return REPORT_LABELS[kind] ?? kind.replace(/_/g, " ");
}

export function executionPhaseLabel(phase: StrategyExecutionPhase | undefined): string {
  if (phase === "warming") return "Warming";
  if (phase === "ready") return "Ready";
  return "Live";
}

export function warmupProgressLabel(strategy: Strategy): string | null {
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

export function startupStatusLabel(job: AiStrategyStartupJob): string {
  if (job.status === "failed") return "Startup failed";
  if (job.status === "completed") return "Startup done";
  if (job.status === "cancelled") return "Startup cancelled";

  const explicit = (job.status_message || "").trim();
  if (explicit) {
    // Keep the tag short — full message belongs in the Startup card.
    if (explicit.length <= 42) return explicit;
    return `${explicit.slice(0, 39)}…`;
  }

  const loopIndex = Number(job.loop_index || 0);
  const loopTarget = Number(job.loop_target || 0);
  const pending = job.pending_reports ?? [];
  if (job.phase === "ensuring_reports") {
    if (pending.length > 0) {
      return `Waiting · ${humanReportLabel(pending[0])}`;
    }
    return "Startup · reports";
  }
  if (job.phase === "seeding_digest") {
    if (job.last_seed_wait) return "Startup · seeding (LLM wait)";
    return "Startup · seeding";
  }
  if (job.phase === "looping" && loopTarget > 0) {
    return `Startup · ${Math.min(loopIndex + 1, loopTarget)}/${loopTarget}`;
  }
  if (job.status === "queued") return "Startup queued";
  return "Starting up…";
}

export type StartupStepState = "done" | "active" | "pending" | "failed" | "skipped";

export type StartupStep = {
  id: "reports" | "seed" | "loops";
  label: string;
  detail: string;
  state: StartupStepState;
};

export function startupSteps(job: AiStrategyStartupJob): StartupStep[] {
  const status = job.status;
  const phase = job.phase;
  const required = job.required_reports ?? [];
  const pending = job.pending_reports ?? [];
  const skipped = job.skipped_reports ?? [];
  const loopIndex = Number(job.loop_index || 0);
  const loopTarget = Number(job.loop_target || 0);

  const reportsDone =
    status === "completed" ||
    status === "failed" ||
    status === "cancelled" ||
    phase === "seeding_digest" ||
    phase === "looping" ||
    phase === "done";
  const seedDone =
    status === "completed" ||
    status === "failed" ||
    status === "cancelled" ||
    phase === "looping" ||
    phase === "done" ||
    job.seed_digest_version != null;
  const loopsDone = status === "completed";

  let reportsState: StartupStepState = "pending";
  if (status === "failed" && phase === "ensuring_reports") reportsState = "failed";
  else if (reportsDone) reportsState = "done";
  else if (phase === "ensuring_reports" || status === "queued") reportsState = "active";

  let seedState: StartupStepState = "pending";
  if (status === "failed" && phase === "seeding_digest") seedState = "failed";
  else if (seedDone) seedState = "done";
  else if (phase === "seeding_digest") seedState = "active";

  let loopsState: StartupStepState = "pending";
  if (status === "failed" && phase === "looping") loopsState = "failed";
  else if (loopsDone) loopsState = "done";
  else if (phase === "looping") loopsState = "active";

  const reportParts: string[] = [];
  for (const kind of required) {
    if (skipped.includes(kind)) reportParts.push(`${humanReportLabel(kind)} skipped`);
    else if (pending.includes(kind)) reportParts.push(`${humanReportLabel(kind)} waiting`);
    else if (reportsDone || phase !== "ensuring_reports") {
      reportParts.push(`${humanReportLabel(kind)} ready`);
    } else {
      reportParts.push(humanReportLabel(kind));
    }
  }

  return [
    {
      id: "reports",
      label: "1. Research reports",
      detail: reportParts.length > 0 ? reportParts.join(" · ") : "No reports required",
      state: reportsState,
    },
    {
      id: "seed",
      label: "2. Seed memory",
      detail:
        job.seed_digest_version != null
          ? `Digest v${job.seed_digest_version}`
          : job.last_seed_wait
            ? `Waiting: ${job.last_seed_wait}`
            : phase === "seeding_digest"
              ? "Generating digest from research…"
              : "After reports",
      state: seedState,
    },
    {
      id: "loops",
      label: "3. Improve loops",
      detail:
        loopTarget > 0
          ? `${Math.min(loopIndex + (phase === "looping" && job.current_backtest_run_id ? 1 : 0), loopTarget)}/${loopTarget} (explore → trade)`
          : "Explore then trade",
      state: loopsState,
    },
  ];
}

export function activityKindLabel(kind: string): string {
  switch (kind) {
    case "startup":
      return "Startup";
    case "backtest":
      return "Signal review";
    case "digest":
      return "Memory";
    case "learning":
      return "Learning";
    case "lifecycle":
      return "Lifecycle";
    case "version":
      return "Params";
    default:
      return kind;
  }
}

export function activityStatusClass(status: string): string {
  if (status === "failed") return "ai-strategy-log-status--failed";
  if (status === "running" || status === "queued") return "ai-strategy-log-status--active";
  if (status === "completed") return "ai-strategy-log-status--completed";
  if (status === "cancelled") return "ai-strategy-log-status--cancelled";
  return "ai-strategy-log-status--info";
}

export function isActiveActivityEvent(event: AiStrategyActivityEvent): boolean {
  return event.status === "running" || event.status === "queued";
}
