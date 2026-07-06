import { useRef, useState } from "react";

type Props = {
  open: boolean;
  busy: boolean;
  onClose: () => void;
  onImport: (file: File, label: string, restore: boolean) => void;
};

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function BackupImportDialog({ open, busy, onClose, onImport }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [label, setLabel] = useState("");
  const [restore, setRestore] = useState(false);

  if (!open) return null;

  function reset() {
    setFile(null);
    setLabel("");
    setRestore(false);
    if (inputRef.current) inputRef.current.value = "";
  }

  function handleClose() {
    if (busy) return;
    reset();
    onClose();
  }

  return (
    <div className="confirm-overlay" role="presentation" onClick={handleClose}>
      <div
        className={`confirm-dialog${restore ? " confirm-dialog--error" : ""}`}
        role="dialog"
        aria-labelledby="import-backup-title"
        onClick={(event) => event.stopPropagation()}
      >
        <h4 id="import-backup-title">Import</h4>
        <p>Upload a JSON backup file exported from BrokerAI. Import always creates a full backup row.</p>

        <label className="backup-create-label">
          Backup file
          <input
            ref={inputRef}
            type="file"
            accept=".json,application/json"
            disabled={busy}
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
        {file ? (
          <p className="settings-muted backup-import-file-meta">
            {file.name} · {formatFileSize(file.size)}
          </p>
        ) : null}

        <label className="backup-create-label">
          Label (optional)
          <input
            type="text"
            value={label}
            maxLength={120}
            disabled={busy}
            onChange={(event) => setLabel(event.target.value)}
            placeholder="Imported from laptop"
          />
        </label>

        <label className="backup-import-restore">
          <input
            type="checkbox"
            checked={restore}
            disabled={busy}
            onChange={(event) => setRestore(event.target.checked)}
          />
          Restore configuration immediately
        </label>
        {restore ? (
          <p className="confirm-warning">
            This replaces current settings with the imported snapshot. A safety change snapshot is
            created first. Backups may contain API secrets.
          </p>
        ) : null}

        <div className="confirm-actions">
          <button type="button" className="btn btn-secondary" disabled={busy} onClick={handleClose}>
            Cancel
          </button>
          <button
            type="button"
            className={restore ? "btn btn-danger" : "btn"}
            disabled={busy || !file}
            onClick={() => {
              if (!file) return;
              onImport(file, label.trim(), restore);
            }}
          >
            {busy ? "Importing…" : restore ? "Import and restore" : "Import"}
          </button>
        </div>
      </div>
    </div>
  );
}
