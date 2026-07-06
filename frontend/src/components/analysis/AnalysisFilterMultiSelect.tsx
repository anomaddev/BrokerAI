import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";

export type AnalysisFilterOption<T extends string> = {
  value: T;
  label: string;
};

type AnalysisFilterMultiSelectProps<T extends string> = {
  label: string;
  ariaLabel: string;
  options: readonly AnalysisFilterOption<T>[];
  value: Set<T>;
  onChange: (value: Set<T>) => void;
};

export default function AnalysisFilterMultiSelect<T extends string>({
  label,
  ariaLabel,
  options,
  value,
  onChange,
}: AnalysisFilterMultiSelectProps<T>) {
  const [open, setOpen] = useState(false);
  const [panelStyle, setPanelStyle] = useState<CSSProperties>({});
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return;

    function updatePanelPosition() {
      const trigger = triggerRef.current;
      if (!trigger) return;
      const rect = trigger.getBoundingClientRect();
      setPanelStyle({
        position: "fixed",
        top: rect.bottom + 6,
        left: rect.left,
        minWidth: rect.width,
        zIndex: 200,
      });
    }

    updatePanelPosition();
    window.addEventListener("resize", updatePanelPosition);
    window.addEventListener("scroll", updatePanelPosition, true);
    return () => {
      window.removeEventListener("resize", updatePanelPosition);
      window.removeEventListener("scroll", updatePanelPosition, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;

    function handlePointerDown(event: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  function toggleOption(option: T) {
    const next = new Set(value);
    if (next.has(option)) {
      next.delete(option);
    } else {
      next.add(option);
    }
    onChange(next);
  }

  return (
    <div className="research-multiselect analysis-toolbar-multiselect" ref={rootRef}>
      <div className="research-multiselect-wrap">
        <button
          ref={triggerRef}
          type="button"
          className="research-multiselect-trigger"
          onClick={() => setOpen((prev) => !prev)}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-label={ariaLabel}
        >
          {label}
        </button>
      </div>
      {open ? (
        <div
          className="research-multiselect-panel analysis-toolbar-multiselect-panel"
          style={panelStyle}
          role="listbox"
          aria-multiselectable="true"
          onPointerDown={(event) => event.stopPropagation()}
        >
          {options.map((option) => {
            const checked = value.has(option.value);
            return (
              <label
                key={option.value}
                className={`research-multiselect-option${checked ? " research-multiselect-option--checked" : ""}`}
                onClick={() => toggleOption(option.value)}
              >
                <input type="checkbox" checked={checked} readOnly tabIndex={-1} />
                <span>{option.label}</span>
              </label>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
