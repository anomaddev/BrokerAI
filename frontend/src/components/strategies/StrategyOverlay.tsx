type StrategyOverlayProps = {
  children: React.ReactNode;
  onClose: () => void;
  wide?: boolean;
  extraWide?: boolean;
  titleId?: string;
  dialogClassName?: string;
};

export default function StrategyOverlay({
  children,
  onClose,
  wide,
  extraWide,
  titleId,
  dialogClassName,
}: StrategyOverlayProps) {
  const dialogClass = [
    "model-overlay-dialog",
    wide || extraWide ? "model-overlay-dialog--wide" : "",
    extraWide ? "model-overlay-dialog--create-strategy" : "",
    dialogClassName ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="confirm-overlay" role="presentation" onClick={onClose}>
      <div
        className={dialogClass}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
