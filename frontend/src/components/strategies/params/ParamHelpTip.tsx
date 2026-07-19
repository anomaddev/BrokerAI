import { useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";

type TooltipCoords = {
  top: number;
  left: number;
};

type ParamHelpTipProps = {
  label: string;
  title: string;
  body: string;
};

const VIEWPORT_PADDING = 8;
const GAP = 8;

function clampTooltipPosition(
  buttonRect: DOMRect,
  tipWidth: number,
  tipHeight: number,
): TooltipCoords {
  const halfWidth = tipWidth / 2;
  const minCenter = VIEWPORT_PADDING + halfWidth;
  const maxCenter = window.innerWidth - VIEWPORT_PADDING - halfWidth;
  const preferredCenter = buttonRect.left + buttonRect.width / 2;
  const left =
    maxCenter >= minCenter
      ? Math.min(Math.max(preferredCenter, minCenter), maxCenter)
      : window.innerWidth / 2;

  const belowTop = buttonRect.bottom + GAP;
  const aboveTop = buttonRect.top - GAP - tipHeight;
  const fitsBelow = belowTop + tipHeight <= window.innerHeight - VIEWPORT_PADDING;
  const fitsAbove = aboveTop >= VIEWPORT_PADDING;
  let top = fitsBelow || !fitsAbove ? belowTop : aboveTop;
  top = Math.min(
    Math.max(top, VIEWPORT_PADDING),
    Math.max(VIEWPORT_PADDING, window.innerHeight - VIEWPORT_PADDING - tipHeight),
  );

  return { top, left };
}

export default function ParamHelpTip({ label, title, body }: ParamHelpTipProps) {
  const tipId = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState<TooltipCoords | null>(null);

  useLayoutEffect(() => {
    if (!open) {
      setCoords(null);
      return;
    }

    function updatePosition() {
      const button = buttonRef.current;
      const tip = tooltipRef.current;
      if (!button || !tip) return;
      const next = clampTooltipPosition(
        button.getBoundingClientRect(),
        tip.offsetWidth,
        tip.offsetHeight,
      );
      setCoords((prev) =>
        prev && prev.top === next.top && prev.left === next.left ? prev : next,
      );
    }

    updatePosition();
    window.addEventListener("scroll", updatePosition, true);
    window.addEventListener("resize", updatePosition);

    return () => {
      window.removeEventListener("scroll", updatePosition, true);
      window.removeEventListener("resize", updatePosition);
    };
  }, [open, title, body]);

  const tooltipNode = open
    ? createPortal(
        <div
          ref={tooltipRef}
          id={tipId}
          className="param-help-tooltip"
          role="tooltip"
          style={
            coords
              ? { top: coords.top, left: coords.left }
              : { top: 0, left: 0, visibility: "hidden" }
          }
        >
          <p className="param-help-tooltip-title">{title}</p>
          <p className="param-help-tooltip-body">{body}</p>
        </div>,
        document.body,
      )
    : null;

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className="param-help-btn"
        aria-label={`About ${label}`}
        aria-describedby={open ? tipId : undefined}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
        }}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <Info size={14} aria-hidden="true" />
      </button>
      {tooltipNode}
    </>
  );
}
