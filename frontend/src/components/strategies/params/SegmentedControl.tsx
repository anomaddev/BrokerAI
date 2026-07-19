import type { ReactNode } from "react";

type SegmentedOption<T extends string> = {
  value: T;
  label: string;
};

type SegmentedControlProps<T extends string> = {
  label: string;
  value: T;
  options: SegmentedOption<T>[];
  readOnly?: boolean;
  /** Optional helper control aligned to the right of the label. */
  labelHelp?: ReactNode;
  onChange: (value: T) => void;
};

export default function SegmentedControl<T extends string>({
  label,
  value,
  options,
  readOnly,
  labelHelp,
  onChange,
}: SegmentedControlProps<T>) {
  const selectedLabel = options.find((option) => option.value === value)?.label ?? value;

  const labelNode = labelHelp ? (
    <div className="param-control-label-with-help">
      <span className="param-control-label">{label}</span>
      {labelHelp}
    </div>
  ) : (
    <span className="param-control-label">{label}</span>
  );

  if (readOnly) {
    return (
      <div className="param-control param-control--readonly">
        <div className="param-control-label-row">{labelNode}</div>
        <span className="param-control-value param-control-value--locked">{selectedLabel}</span>
      </div>
    );
  }

  return (
    <div className="param-control">
      <div className="param-control-label-row">{labelNode}</div>
      <div className="param-segmented" role="tablist" aria-label={label}>
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={value === option.value}
            className={`param-segmented-btn${value === option.value ? " param-segmented-btn--active" : ""}`}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
