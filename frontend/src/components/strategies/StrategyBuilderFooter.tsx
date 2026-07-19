import { useEffect, useRef } from "react";
import { ChevronDown } from "lucide-react";

export const STRATEGY_NOTES_MAX = 2000;

type StrategyBuilderFooterProps = {
  notes: string;
  onNotesChange: (value: string) => void;
  notesExpanded: boolean;
  onNotesExpandedChange: (expanded: boolean) => void;
  canSave: boolean;
  onSave: () => void;
  onCancel: () => void;
  titleEmpty?: boolean;
  onHistory?: () => void;
};

export default function StrategyBuilderFooter({
  notes,
  onNotesChange,
  notesExpanded,
  onNotesExpandedChange,
  canSave,
  onSave,
  onCancel,
  titleEmpty = false,
  onHistory,
}: StrategyBuilderFooterProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const footerRef = useRef<HTMLDivElement>(null);
  const sheetRef = useRef<HTMLDivElement>(null);

  // Keep the overlay seated on the real footer height (avoids gap / jump).
  useEffect(() => {
    const footer = footerRef.current;
    const body = footer?.closest(".strategy-builder-body");
    if (!footer || !(body instanceof HTMLElement)) return;

    const sync = () => {
      body.style.setProperty("--strategy-builder-footer-height", `${footer.offsetHeight}px`);
    };
    sync();

    const observer = new ResizeObserver(sync);
    observer.observe(footer);
    return () => observer.disconnect();
  }, []);

  // Focus after the slide finishes so the chart doesn't jump mid-animation.
  useEffect(() => {
    if (!notesExpanded) return;
    const sheet = sheetRef.current;
    const textarea = textareaRef.current;
    if (!sheet || !textarea) return;

    let focused = false;
    const focusNotes = () => {
      if (focused) return;
      focused = true;
      textarea.focus({ preventScroll: true });
    };

    const onEnd = (event: TransitionEvent) => {
      if (event.target === sheet && event.propertyName === "transform") {
        focusNotes();
      }
    };
    sheet.addEventListener("transitionend", onEnd);
    const fallback = window.setTimeout(focusNotes, 360);
    return () => {
      sheet.removeEventListener("transitionend", onEnd);
      window.clearTimeout(fallback);
    };
  }, [notesExpanded]);

  return (
    <>
      <div
        className={`strategy-builder-notes-layer${notesExpanded ? " strategy-builder-notes-layer--open" : ""}`}
        aria-hidden={!notesExpanded}
      >
        <div ref={sheetRef} className="strategy-builder-notes-sheet">
          <div className="strategy-builder-notes-sheet-inner">
            <label htmlFor="strategy-builder-notes" className="visually-hidden">
              Strategy notes
            </label>
            <textarea
              ref={textareaRef}
              id="strategy-builder-notes"
              className="strategy-builder-notes-input"
              value={notes}
              maxLength={STRATEGY_NOTES_MAX}
              tabIndex={notesExpanded ? 0 : -1}
              placeholder="Write detailed notes — rationale, setup rules, session quirks, things to watch…"
              onChange={(event) => onNotesChange(event.target.value.slice(0, STRATEGY_NOTES_MAX))}
            />
            <span className="strategy-builder-notes-count">
              {notes.length}/{STRATEGY_NOTES_MAX}
            </span>
          </div>
        </div>
      </div>

      <div
        ref={footerRef}
        className={`strategy-builder-footer${notesExpanded ? " strategy-builder-footer--notes-open" : ""}`}
      >
        <div className="strategy-builder-footer-chart">
          <button
            type="button"
            className="strategy-builder-notes-toggle"
            aria-expanded={notesExpanded}
            aria-controls="strategy-builder-notes"
            onClick={() => onNotesExpandedChange(!notesExpanded)}
          >
            <span className="strategy-builder-notes-toggle-label">
              Notes
              <span
                className={`strategy-builder-notes-preview${notes.trim() ? "" : " strategy-builder-notes-preview--empty"}`}
              >
                {notes.trim() || "Add detailed notes about this strategy"}
              </span>
            </span>
            <ChevronDown
              className={`strategy-builder-notes-chevron${notesExpanded ? " strategy-builder-notes-chevron--open" : ""}`}
              size={16}
              aria-hidden="true"
            />
          </button>
        </div>

        <div className="strategy-builder-footer-panel">
          <div
            className={`strategy-builder-footer-actions${onHistory ? " strategy-builder-footer-actions--with-history" : ""}`}
          >
            {onHistory ? (
              <button type="button" className="btn btn-secondary" onClick={onHistory}>
                History
              </button>
            ) : null}
            <button type="button" className="btn btn-secondary" onClick={onCancel}>
              Cancel
            </button>
            <button
              type="button"
              className="btn"
              onClick={onSave}
              disabled={!canSave || titleEmpty}
              title={canSave ? undefined : "Complete required parameters to save"}
            >
              Save
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
