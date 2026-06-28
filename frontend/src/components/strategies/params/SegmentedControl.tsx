type SegmentedOption<T extends string> = {
  value: T;
  label: string;
};

type SegmentedControlProps<T extends string> = {
  label: string;
  value: T;
  options: SegmentedOption<T>[];
  readOnly?: boolean;
  onChange: (value: T) => void;
};

export default function SegmentedControl<T extends string>({
  label,
  value,
  options,
  readOnly,
  onChange,
}: SegmentedControlProps<T>) {
  const selectedLabel = options.find((option) => option.value === value)?.label ?? value;

  if (readOnly) {
    return (
      <div className="param-control param-control--readonly">
        <span className="param-control-label">{label}</span>
        <span className="param-control-value param-control-value--locked">{selectedLabel}</span>
      </div>
    );
  }

  return (
    <div className="param-control">
      <span className="param-control-label">{label}</span>
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
