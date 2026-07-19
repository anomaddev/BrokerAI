import { useEffect, useState, type ReactNode } from "react";

type NumberInputProps = {
  id: string;
  label?: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  suffix?: string;
  formatValue?: (value: number) => string;
  invalid?: boolean;
  inline?: boolean;
  embedded?: boolean;
  readOnly?: boolean;
  /** Optional helper control shown next to the label. */
  labelHelp?: ReactNode;
  onChange: (value: number) => void;
};

const PARTIAL_NUMBER = /^-?\d*\.?\d*$/;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function decimalPlaces(step: number): number {
  const text = String(step);
  const dot = text.indexOf(".");
  return dot === -1 ? 0 : text.length - dot - 1;
}

function snapToStep(value: number, min: number, step: number): number {
  if (step <= 0) return value;
  const snapped = min + Math.round((value - min) / step) * step;
  const dp = decimalPlaces(step);
  return dp === 0 ? snapped : Number(snapped.toFixed(dp));
}

function formatNumber(value: number, step: number, formatValue?: (value: number) => string): string {
  if (formatValue) return formatValue(value);
  const dp = decimalPlaces(step);
  return dp === 0 ? String(Math.round(value)) : value.toFixed(dp);
}

export default function NumberInput({
  id,
  label,
  value,
  min,
  max,
  step = 1,
  unit,
  suffix,
  formatValue,
  invalid,
  inline,
  embedded,
  readOnly,
  labelHelp,
  onChange,
}: NumberInputProps) {
  const display = `${formatNumber(value, step, formatValue)}${unit ? ` ${unit}` : ""}${suffix ?? ""}`;

  const labelNode = label ? (
    labelHelp ? (
      <div className="param-control-label-with-help">
        {readOnly ? (
          <span className="param-control-label">{label}</span>
        ) : (
          <label htmlFor={id} className="param-control-label">
            {label}
          </label>
        )}
        {labelHelp}
      </div>
    ) : readOnly ? (
      <span className="param-control-label">{label}</span>
    ) : (
      <label htmlFor={id} className="param-control-label">
        {label}
      </label>
    )
  ) : null;

  if (readOnly) {
    if (inline) {
      return <span className="param-control-value">{display}</span>;
    }

    return (
      <div className="param-control param-control--readonly">
        {labelNode}
        <span className="param-control-value param-control-value--locked">{display}</span>
      </div>
    );
  }
  const [draft, setDraft] = useState(() => formatNumber(value, step, formatValue));
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) {
      setDraft(formatNumber(value, step, formatValue));
    }
  }, [value, step, formatValue, focused]);

  function commit(raw: string) {
    const parsed = Number(raw);
    if (raw.trim() === "" || Number.isNaN(parsed)) {
      setDraft(formatNumber(value, step, formatValue));
      return;
    }
    const next = snapToStep(clamp(parsed, min, max), min, step);
    onChange(next);
    setDraft(formatNumber(next, step, formatValue));
  }

  const field = (
    <input
      id={id}
      type="text"
      inputMode="decimal"
      className={embedded ? "param-stepper-input" : "param-number-input-field"}
      value={draft}
      aria-invalid={invalid || undefined}
      onChange={(event) => {
        const next = event.target.value;
        if (PARTIAL_NUMBER.test(next)) {
          setDraft(next);
        }
      }}
      onFocus={() => setFocused(true)}
      onBlur={() => {
        setFocused(false);
        commit(draft);
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.currentTarget.blur();
        }
      }}
    />
  );

  if (embedded) return field;

  const input = (
    <div
      className={`param-number-input${inline ? " param-number-input--inline" : ""}${invalid ? " param-number-input--invalid" : ""}`}
    >
      {field}
      {(unit || suffix) && (
        <span className="param-number-input-affix" aria-hidden="true">
          {unit ?? suffix}
        </span>
      )}
    </div>
  );

  if (inline) return input;

  return (
    <div className="param-control">
      {labelNode}
      {input}
    </div>
  );
}
