import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { HexColorPicker } from "react-colorful";

type ColorPickerInputProps = {
  id?: string;
  value: string;
  onChange: (color: string) => void;
  label?: string;
  variant?: "inline" | "param";
};

type PopoverPosition = {
  top: number;
  left: number;
};

export default function ColorPickerInput({
  id,
  value,
  onChange,
  label = "Color",
  variant = "inline",
}: ColorPickerInputProps) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<PopoverPosition | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const swatchRef = useRef<HTMLButtonElement>(null);

  useLayoutEffect(() => {
    if (!open || !swatchRef.current) {
      setPosition(null);
      return;
    }

    function updatePosition() {
      const rect = swatchRef.current?.getBoundingClientRect();
      if (!rect) return;

      const popoverWidth = 160;
      const popoverHeight = 130;
      const gap = 6;

      let left = rect.right - popoverWidth;
      let top = rect.top - popoverHeight - gap;

      if (left < 8) left = 8;
      if (left + popoverWidth > window.innerWidth - 8) {
        left = window.innerWidth - popoverWidth - 8;
      }

      if (top < 8) {
        top = rect.bottom + gap;
      }

      setPosition({ top, left });
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;

    function handleClick(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div
      className={`explore-color-picker explore-color-picker--${variant}${open ? " explore-color-picker--open" : ""}`}
      ref={rootRef}
    >
      <button
        ref={swatchRef}
        id={id}
        type="button"
        className="explore-color-picker-swatch"
        aria-label={label}
        aria-expanded={open}
        style={{ backgroundColor: value }}
        onClick={() => setOpen((current) => !current)}
      />
      {open && position ? (
        <div
          className="explore-color-picker-popover explore-color-picker-popover--fixed"
          role="dialog"
          aria-label={label}
          style={{ top: position.top, left: position.left }}
        >
          <HexColorPicker color={value} onChange={onChange} />
        </div>
      ) : null}
    </div>
  );
}
