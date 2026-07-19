type ParamOptionListOption<T extends string> = {
  value: T;
  label: string;
  description: string;
  /** Optional short tag shown next to the label (e.g. "EMA signal"). */
  badge?: string;
};

type ParamOptionListProps<T extends string> = {
  label: string;
  name: string;
  value: T;
  options: ParamOptionListOption<T>[];
  onChange: (value: T) => void;
};

export default function ParamOptionList<T extends string>({
  label,
  name,
  value,
  options,
  onChange,
}: ParamOptionListProps<T>) {
  return (
    <div className="param-control">
      <span className="param-control-label" id={`${name}-label`}>
        {label}
      </span>
      <div className="param-option-list" role="radiogroup" aria-labelledby={`${name}-label`}>
        {options.map((option) => {
          const selected = value === option.value;
          return (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={selected}
              className={`param-option-list-btn${selected ? " param-option-list-btn--active" : ""}`}
              onClick={() => onChange(option.value)}
            >
              <span className="param-option-list-title-row">
                <span className="param-option-list-label">{option.label}</span>
                {option.badge ? (
                  <span className="param-option-list-badge">{option.badge}</span>
                ) : null}
              </span>
              <span className="param-option-list-desc">{option.description}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
