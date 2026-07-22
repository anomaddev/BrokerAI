import { useEffect, useState, type ReactNode } from "react";
import { useIsMobile } from "../hooks/useMediaQuery";

type MobileSheetAsideProps = {
  /** Extra classes merged onto the aside (e.g. analysis-run-panel-col). */
  className?: string;
  /** Label for the floating action button that opens the sheet on mobile. */
  fabLabel: string;
  children: ReactNode;
};

/**
 * Desktop: normal aside in the layout flow.
 * Mobile (≤768px): collapses into a bottom sheet opened via a FAB.
 *
 * CSS for `.mobile-sheet-panel*` lives in base.css and must stay after base
 * panel rules so cascade wins. Edge case: leaving mobile closes the sheet.
 */
export default function MobileSheetAside({
  className = "",
  fabLabel,
  children,
}: MobileSheetAsideProps) {
  const isMobile = useIsMobile();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!isMobile) setOpen(false);
  }, [isMobile]);

  const asideClass = [
    "mobile-sheet-panel",
    className,
    open ? "mobile-sheet-panel--open" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <>
      <aside className={asideClass}>
        <div className="mobile-sheet-panel-handle" aria-hidden="true" />
        {isMobile ? (
          <div className="mobile-sheet-panel-toolbar">
            <span className="mobile-sheet-panel-toolbar-label">{fabLabel}</span>
            <button
              type="button"
              className="mobile-sheet-panel-close"
              onClick={() => setOpen(false)}
            >
              Done
            </button>
          </div>
        ) : null}
        <div className="mobile-sheet-panel-body">{children}</div>
      </aside>
      {isMobile && !open ? (
        <button
          type="button"
          className="mobile-sheet-panel-fab"
          onClick={() => setOpen(true)}
        >
          {fabLabel}
        </button>
      ) : null}
      {isMobile && open ? (
        <button
          type="button"
          className="mobile-sheet-scrim"
          aria-label={`Close ${fabLabel}`}
          onClick={() => setOpen(false)}
        />
      ) : null}
    </>
  );
}
