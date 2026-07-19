type ReplaceStrategyEditsDialogProps = {
  open: boolean;
  onCancel: () => void;
  onConfirm: () => void;
};

export default function ReplaceStrategyEditsDialog({
  open,
  onCancel,
  onConfirm,
}: ReplaceStrategyEditsDialogProps) {
  if (!open) return null;

  return (
    <div className="confirm-overlay" role="presentation" onClick={onCancel}>
      <div
        className="confirm-dialog"
        role="alertdialog"
        aria-labelledby="replace-strategy-edits-title"
        aria-describedby="replace-strategy-edits-message"
        onClick={(event) => event.stopPropagation()}
      >
        <h4 id="replace-strategy-edits-title">Replace current edits?</h4>
        <p id="replace-strategy-edits-message">
          Loading this version will replace your unsaved changes in the builder.
        </p>
        <div className="confirm-actions">
          <button type="button" className="btn btn-secondary" onClick={onCancel}>
            Keep editing
          </button>
          <button type="button" className="btn" onClick={onConfirm}>
            Load version
          </button>
        </div>
      </div>
    </div>
  );
}
