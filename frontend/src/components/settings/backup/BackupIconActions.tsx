import { Download, RotateCcw, Trash2 } from "lucide-react";
import type { ConfigBackupSummary } from "../../api/client";

type Props = {
  backup: ConfigBackupSummary;
  downloading?: boolean;
  onDownload?: (backup: ConfigBackupSummary) => void;
  onRestore?: (backup: ConfigBackupSummary) => void;
  onDelete?: (backup: ConfigBackupSummary) => void;
};

export default function BackupIconActions({
  backup,
  downloading = false,
  onDownload,
  onRestore,
  onDelete,
}: Props) {
  return (
    <div className="backup-icon-actions">
      {onDownload ? (
        <button
          type="button"
          className="backup-icon-btn"
          title={downloading ? "Downloading…" : "Download"}
          aria-label={downloading ? "Downloading" : "Download"}
          disabled={downloading}
          onClick={() => onDownload(backup)}
        >
          <Download size={15} strokeWidth={2} />
        </button>
      ) : null}
      {onRestore ? (
        <button
          type="button"
          className="backup-icon-btn backup-icon-btn--primary"
          title="Restore"
          aria-label="Restore"
          onClick={() => onRestore(backup)}
        >
          <RotateCcw size={15} strokeWidth={2} />
        </button>
      ) : null}
      {onDelete ? (
        <button
          type="button"
          className="backup-icon-btn backup-icon-btn--danger"
          title="Delete"
          aria-label="Delete"
          onClick={() => onDelete(backup)}
        >
          <Trash2 size={15} strokeWidth={2} />
        </button>
      ) : null}
    </div>
  );
}
