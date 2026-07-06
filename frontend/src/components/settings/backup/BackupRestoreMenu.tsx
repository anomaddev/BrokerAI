import { useEffect, useRef, useState } from "react";
import { MoreHorizontal } from "lucide-react";
import type { ConfigBackupRestoreScope, ConfigBackupSummary } from "../../../api/client";

type Props = {
  backup: ConfigBackupSummary;
  onRestore: (backup: ConfigBackupSummary, scope: ConfigBackupRestoreScope) => void;
};

export default function BackupRestoreMenu({ backup, onRestore }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  return (
    <div className="backup-restore-menu" ref={rootRef}>
      <button
        type="button"
        className="backup-icon-btn"
        title="Restore options"
        aria-label="Restore options"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <MoreHorizontal size={15} strokeWidth={2} />
      </button>
      {open ? (
        <div className="backup-restore-menu__panel" role="menu">
          <button
            type="button"
            className="backup-restore-menu__item"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onRestore(backup, "setting");
            }}
          >
            Restore Only This
          </button>
          <button
            type="button"
            className="backup-restore-menu__item"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onRestore(backup, "full");
            }}
          >
            Rollback All to Here
          </button>
        </div>
      ) : null}
    </div>
  );
}
