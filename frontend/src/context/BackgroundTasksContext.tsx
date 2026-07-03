import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  api,
  BACKGROUND_TASK_COMPLETED_EVENT,
  type BackgroundTask,
  type BackgroundTaskCompletedDetail,
} from "../api/client";

type BackgroundTasksContextValue = {
  activeTask: BackgroundTask | null;
  recentTask: BackgroundTask | null;
  dismissRecentTask: () => void;
  watchBackgroundTasks: () => void;
  showFooterNotice: (notice: FooterNoticeInput) => void;
  isTaskKindActive: (kind: string) => boolean;
  isResearchTaskActive: () => boolean;
};

type FooterNoticeInput = {
  label: string;
  message: string;
  status: Exclude<BackgroundTask["status"], "running">;
};

const BackgroundTasksContext = createContext<BackgroundTasksContextValue | null>(null);

const RESEARCH_KINDS = new Set([
  "research_daily",
  "research_daily_rerun",
  "research_weekly_brief",
  "research_weekly_debrief",
]);

const SUCCESS_DISMISS_MS = 5000;
const TERMINAL_DISMISS_MS = 8000;
const POLL_INTERVAL_MS = 2500;

function tasksEqual(a: BackgroundTask | null, b: BackgroundTask | null): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  return (
    a.id === b.id &&
    a.status === b.status &&
    a.progress === b.progress &&
    a.step === b.step &&
    a.message === b.message
  );
}

function dispatchCompleted(task: BackgroundTask) {
  const detail: BackgroundTaskCompletedDetail = {
    kind: task.kind,
    status: task.status,
    result: task.result ?? null,
    error: task.error ?? null,
  };
  window.dispatchEvent(
    new CustomEvent(BACKGROUND_TASK_COMPLETED_EVENT, { detail }),
  );
}

export function BackgroundTasksProvider({ children }: { children: ReactNode }) {
  const [activeTask, setActiveTask] = useState<BackgroundTask | null>(null);
  const [recentTask, setRecentTask] = useState<BackgroundTask | null>(null);
  const seenTaskIdsRef = useRef<Set<string>>(new Set());
  const dismissTimerRef = useRef<number | null>(null);
  const pollTimerRef = useRef<number | null>(null);
  const activeTaskRef = useRef<BackgroundTask | null>(null);
  const pollingRef = useRef(false);

  const clearDismissTimer = useCallback(() => {
    if (dismissTimerRef.current !== null) {
      window.clearTimeout(dismissTimerRef.current);
      dismissTimerRef.current = null;
    }
  }, []);

  const stopPolling = useCallback(() => {
    pollingRef.current = false;
    if (pollTimerRef.current !== null) {
      window.clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const dismissRecentTask = useCallback(() => {
    clearDismissTimer();
    setRecentTask(null);
  }, [clearDismissTimer]);

  const showRecentTask = useCallback(
    (task: BackgroundTask) => {
      clearDismissTimer();
      setRecentTask(task);
      if (task.status !== "running") {
        const dismissMs = task.status === "success" ? SUCCESS_DISMISS_MS : TERMINAL_DISMISS_MS;
        dismissTimerRef.current = window.setTimeout(() => {
          setRecentTask(null);
          dismissTimerRef.current = null;
        }, dismissMs);
      }
    },
    [clearDismissTimer],
  );

  const showFooterNotice = useCallback(
    (notice: FooterNoticeInput) => {
      const now = new Date().toISOString();
      showRecentTask({
        id: `notice-${Date.now()}`,
        kind: "notice",
        label: notice.label,
        message: notice.message,
        status: notice.status,
        step: "done",
        progress: 100,
        started_at: now,
        finished_at: now,
        cancellable: false,
      });
    },
    [showRecentTask],
  );

  const applyRecentTask = useCallback(
    (task: BackgroundTask) => {
      if (task.status === "running" || seenTaskIdsRef.current.has(task.id)) {
        return;
      }
      seenTaskIdsRef.current.add(task.id);
      showRecentTask(task);
      if (
        task.status === "success" ||
        task.status === "failed" ||
        task.status === "skipped" ||
        task.status === "cancelled"
      ) {
        dispatchCompleted(task);
      }
    },
    [showRecentTask],
  );

  const setActiveTaskIfChanged = useCallback((next: BackgroundTask | null) => {
    if (tasksEqual(activeTaskRef.current, next)) {
      return false;
    }
    activeTaskRef.current = next;
    setActiveTask(next);
    return true;
  }, []);

  const loadRecentCompletion = useCallback(async () => {
    try {
      const { tasks } = await api.getRecentBackgroundTasks(3);
      const latestRecent = tasks[0] ?? null;
      if (latestRecent) {
        applyRecentTask(latestRecent);
      }
    } catch {
      // Ignore completion fetch errors.
    }
  }, [applyRecentTask]);

  const pollActiveTask = useCallback(async () => {
    try {
      const { task } = await api.getActiveBackgroundTask();
      const wasRunning = activeTaskRef.current?.status === "running";
      setActiveTaskIfChanged(task);

      if (task?.status === "running") {
        return;
      }

      stopPolling();

      if (wasRunning) {
        await loadRecentCompletion();
      }
    } catch {
      stopPolling();
    }
  }, [loadRecentCompletion, setActiveTaskIfChanged, stopPolling]);

  const startPolling = useCallback(() => {
    if (pollingRef.current) {
      return;
    }
    pollingRef.current = true;
    pollTimerRef.current = window.setInterval(() => {
      void pollActiveTask();
    }, POLL_INTERVAL_MS);
  }, [pollActiveTask]);

  const watchBackgroundTasks = useCallback(() => {
    void (async () => {
      await pollActiveTask();
      if (activeTaskRef.current?.status === "running") {
        startPolling();
      }
    })();
  }, [pollActiveTask, startPolling]);

  useEffect(() => {
    void (async () => {
      try {
        const { tasks } = await api.getRecentBackgroundTasks(10);
        tasks.forEach((task) => seenTaskIdsRef.current.add(task.id));
      } catch {
        // Ignore seed failures.
      }

      await pollActiveTask();
      if (activeTaskRef.current?.status === "running") {
        startPolling();
      }
    })();

    return () => {
      stopPolling();
      clearDismissTimer();
    };
  }, [clearDismissTimer, pollActiveTask, startPolling, stopPolling]);

  const value = useMemo<BackgroundTasksContextValue>(
    () => ({
      activeTask,
      recentTask,
      dismissRecentTask,
      watchBackgroundTasks,
      showFooterNotice,
      isTaskKindActive: (kind: string) =>
        activeTask?.status === "running" && activeTask.kind === kind,
      isResearchTaskActive: () =>
        activeTask?.status === "running" && RESEARCH_KINDS.has(activeTask.kind),
    }),
    [activeTask, recentTask, dismissRecentTask, watchBackgroundTasks, showFooterNotice],
  );

  return (
    <BackgroundTasksContext.Provider value={value}>
      {children}
    </BackgroundTasksContext.Provider>
  );
}

export function useBackgroundTasks() {
  const context = useContext(BackgroundTasksContext);
  if (!context) {
    throw new Error("useBackgroundTasks must be used within BackgroundTasksProvider");
  }
  return context;
}
