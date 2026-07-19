type DiscardStrategyChangesDialogProps = {
  open: boolean;
  onCancel: () => void;
  onDiscard: () => void;
};

export default function DiscardStrategyChangesDialog({
  open,
  onCancel,
  onDiscard,
}: DiscardStrategyChangesDialogProps) {
  if (!open) return null;

  return (
    <div className="confirm-overlay" role="presentation" onClick={onCancel}>
      <div
        className="confirm-dialog"
        role="alertdialog"
        aria-labelledby="discard-strategy-title"
        aria-describedby="discard-strategy-message"
        onClick={(event) => event.stopPropagation()}
      >
        <h4 id="discard-strategy-title">Are you sure?</h4>
        <p id="discard-strategy-message">
          You have unsaved changes. Closing will discard them.
        </p>
        <div className="confirm-actions">
          <button type="button" className="btn btn-secondary" onClick={onCancel}>
            Keep editing
          </button>
          <button type="button" className="btn btn-danger" onClick={onDiscard}>
            Discard
          </button>
        </div>
      </div>
    </div>
  );
}
