import type { ReactNode } from "react";

type ParamSelectOption<T extends string> = {
  value: T;
  label: string;
};

type ParamSelectProps<T extends string> = {
  id: string;
  label: string;
  value: T;
  options: ParamSelectOption<T>[];
  /** Optional helper control shown next to the label. */
  labelHelp?: ReactNode;
  onChange: (value: T) => void;
};

export default function ParamSelect<T extends string>({
  id,
  label,
  value,
  options,
  labelHelp,
  onChange,
}: ParamSelectProps<T>) {
  const labelNode = labelHelp ? (
    <div className="param-control-label-with-help">
      <label htmlFor={id} className="param-control-label">
        {label}
      </label>
      {labelHelp}
    </div>
  ) : (
    <label htmlFor={id} className="param-control-label">
      {label}
    </label>
  );

  return (
    <div className="param-control">
      {labelNode}
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
