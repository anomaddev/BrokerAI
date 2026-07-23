import { Link } from "react-router-dom";
import {
  REPORT_KIND_LABELS,
  type ReportKind,
} from "../../pages/strategies/presets/aiStrategy/reportSettingsPrompt";

type EnableReportsPromptDialogProps = {
  open: boolean;
  kinds: ReportKind[];
  phase: "confirm" | "enabled";
  busy?: boolean;
  error?: string | null;
  onCancel: () => void;
  onConfirm: () => void;
  onDismissEnabled: () => void;
};

export default function EnableReportsPromptDialog({
  open,
  kinds,
  phase,
  busy = false,
  error = null,
  onCancel,
  onConfirm,
  onDismissEnabled,
}: EnableReportsPromptDialogProps) {
  if (!open || kinds.length === 0) return null;

  const labels = kinds.map((kind) => REPORT_KIND_LABELS[kind]);
  const listText =
    labels.length === 1
      ? labels[0]
      : `${labels.slice(0, -1).join(", ")}, and ${labels[labels.length - 1]}`;

  if (phase === "enabled") {
    return (
      <div className="confirm-overlay" role="presentation" onClick={onDismissEnabled}>
        <div
          className="confirm-dialog"
          role="alertdialog"
          aria-labelledby="enable-reports-enabled-title"
          aria-describedby="enable-reports-enabled-message"
          onClick={(event) => event.stopPropagation()}
        >
          <h4 id="enable-reports-enabled-title">Reports enabled</h4>
          <p id="enable-reports-enabled-message">
            {listText} {labels.length === 1 ? "is" : "are"} now on with the default schedule.
            Check Settings → Reports to set the time you want {labels.length === 1 ? "it" : "them"}{" "}
            to run, and confirm models are selected.
          </p>
          <div className="confirm-actions">
            <Link to="/settings/reports" className="btn btn-secondary" onClick={onDismissEnabled}>
              Open Reports settings
            </Link>
            <button type="button" className="btn" onClick={onDismissEnabled}>
              Got it
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="confirm-overlay" role="presentation" onClick={busy ? undefined : onCancel}>
      <div
        className="confirm-dialog"
        role="alertdialog"
        aria-labelledby="enable-reports-title"
        aria-describedby="enable-reports-message"
        onClick={(event) => event.stopPropagation()}
      >
        <h4 id="enable-reports-title">Enable report schedules?</h4>
        <p id="enable-reports-message">
          This AI Strategy uses {listText}, but {labels.length === 1 ? "that report is" : "those reports are"}{" "}
          turned off in Settings → Reports. Enable {labels.length === 1 ? "it" : "them"} with the
          default schedule now?
        </p>
        {error ? (
          <p className="param-helper param-helper--warn" role="alert">
            {error}
          </p>
        ) : null}
        <div className="confirm-actions">
          <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>
            Not now
          </button>
          <button type="button" className="btn" onClick={onConfirm} disabled={busy}>
            {busy ? "Enabling…" : "Enable"}
          </button>
        </div>
      </div>
    </div>
  );
}
