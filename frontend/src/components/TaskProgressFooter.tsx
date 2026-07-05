import { Link } from "react-router-dom";
import { ROUTES } from "../lib/routes";
import { useCallback, useState } from "react";
import { X } from "lucide-react";
import { api } from "../api/client";
import { useBackgroundTasks } from "../context/BackgroundTasksContext";
import type { BackgroundTask } from "../api/client";

function reportLinkFromTask(task: BackgroundTask): string | null {
  const reportPath = task.result?.report_path;
  if (typeof reportPath !== "string" || !reportPath) {
    return null;
  }
  const filename = reportPath.split("/").slice(-2).join("/");
  return filename ? ROUTES.research.reportView(filename) : null;
}

export default function TaskProgressFooter() {
  const { activeTask, recentTask, dismissRecentTask, watchBackgroundTasks } =
    useBackgroundTasks();
  const [cancelling, setCancelling] = useState(false);
  const task = activeTask ?? recentTask;

  const handleCancel = useCallback(async () => {
    if (!task || task.status !== "running" || cancelling) {
      return;
    }
    setCancelling(true);
    try {
      await api.cancelBackgroundTask(task.id);
      watchBackgroundTasks();
    } catch {
      // Poll will reflect server state.
    } finally {
      setCancelling(false);
    }
  }, [cancelling, task, watchBackgroundTasks]);

  if (!task) {
    return null;
  }

  const isRunning = task.status === "running";
  const isSuccess = task.status === "success";
  const isFailed = task.status === "failed";
  const isSkipped = task.status === "skipped";
  const isCancelled = task.status === "cancelled";
  const reportLink = isSuccess ? reportLinkFromTask(task) : null;
  const showCancel = isRunning && (task.cancellable ?? true);

  return (
    <footer
      className={`task-progress-footer${
        isSuccess ? " task-progress-footer--success" : ""
      }${isFailed ? " task-progress-footer--failed" : ""}${
        isSkipped ? " task-progress-footer--skipped" : ""
      }${isCancelled ? " task-progress-footer--cancelled" : ""}`}
      role="status"
      aria-live="polite"
    >
      <div className="task-progress-footer__content">
        <div className="task-progress-footer__main">
          <span className="task-progress-footer__label">{task.label}</span>
          {task.message ? (
            <span className="task-progress-footer__message">{task.message}</span>
          ) : null}
          {reportLink ? (
            <Link className="task-progress-footer__link" to={reportLink}>
              View report
            </Link>
          ) : null}
        </div>

        {showCancel ? (
          <button
            type="button"
            className="task-progress-footer__cancel"
            disabled={cancelling || Boolean(task.cancel_requested_at)}
            onClick={() => void handleCancel()}
          >
            {task.cancel_requested_at || cancelling ? "Cancelling…" : "Cancel"}
          </button>
        ) : null}

        {!isRunning ? (
          <button
            type="button"
            className="task-progress-footer__dismiss"
            aria-label="Dismiss"
            onClick={dismissRecentTask}
          >
            <X size={16} aria-hidden="true" />
          </button>
        ) : null}
      </div>

      {isRunning ? (
        <div
          className="update-progress task-progress-footer__track"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={task.progress}
          aria-label={task.label}
        >
          <div
            className="update-progress-bar"
            style={{ width: `${Math.max(task.progress, 4)}%` }}
          />
        </div>
      ) : null}
    </footer>
  );
}
