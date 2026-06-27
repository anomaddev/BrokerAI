type StrategyOverlayProps = {
  children: React.ReactNode;
  onClose: () => void;
  wide?: boolean;
  extraWide?: boolean;
  titleId?: string;
};

export default function StrategyOverlay({
  children,
  onClose,
  wide,
  extraWide,
  titleId,
}: StrategyOverlayProps) {
  const dialogClass = [
    "model-overlay-dialog",
    wide || extraWide ? "model-overlay-dialog--wide" : "",
    extraWide ? "model-overlay-dialog--create-strategy" : "",
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
