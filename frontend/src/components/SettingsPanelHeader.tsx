import type { ReactNode } from "react";

type SaveStatus = "idle" | "saving" | "saved" | "error";

type SettingsPanelHeaderProps = {
  title: string;
  description?: ReactNode;
  message?: string | null;
  error?: string | null;
  saveStatus?: SaveStatus;
  action?: ReactNode;
};

function saveStatusLabel(status: SaveStatus): string | null {
  switch (status) {
    case "saving":
      return "Saving…";
    case "saved":
      return "Saved";
    default:
      return null;
  }
}

export default function SettingsPanelHeader({
  title,
  description,
  message,
  error,
  saveStatus = "idle",
  action,
}: SettingsPanelHeaderProps) {
  const statusLabel = saveStatusLabel(saveStatus);
  const headerAction =
    action ??
    (statusLabel ? <span className="settings-save-status">{statusLabel}</span> : null);

  return (
    <div className="settings-panel-header settings-panel-header--sticky">
      <div className="settings-section-intro">
        <h2 className="settings-panel-title">{title}</h2>
        {description ? <p className="settings-panel-desc">{description}</p> : null}
        {message ? (
          <p className="settings-message settings-panel-header-message">{message}</p>
        ) : null}
        {error ? <p className="settings-error settings-panel-header-message">{error}</p> : null}
      </div>
      {headerAction}
    </div>
  );
}
