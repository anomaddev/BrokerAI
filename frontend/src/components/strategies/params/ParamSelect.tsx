type ParamSelectOption<T extends string> = {
  value: T;
  label: string;
};

type ParamSelectProps<T extends string> = {
  id: string;
  label: string;
  value: T;
  options: ParamSelectOption<T>[];
  onChange: (value: T) => void;
};

export default function ParamSelect<T extends string>({
  id,
  label,
  value,
  options,
  onChange,
}: ParamSelectProps<T>) {
  return (
    <div className="param-control">
      <label htmlFor={id} className="param-control-label">
        {label}
      </label>
      <div className="research-select-wrap">
        <select
          id={id}
          className="research-select"
          value={value}
          aria-label={label}
          onChange={(event) => onChange(event.target.value as T)}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
