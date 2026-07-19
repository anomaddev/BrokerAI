import type { ReactNode } from "react";
import ToggleSwitch from "../../ToggleSwitch";

type ParamToggleRowProps = {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** Optional helper control shown next to the label. */
  labelHelp?: ReactNode;
  children?: ReactNode;
};

export default function ParamToggleRow({
  label,
  checked,
  onChange,
  labelHelp,
  children,
}: ParamToggleRowProps) {
  return (
    <div className="param-toggle-row">
      <div className="param-toggle-row-header">
        <div className="param-toggle-row-label">
          <span className="param-control-label">{label}</span>
          {labelHelp}
        </div>
        <ToggleSwitch checked={checked} onChange={onChange} label={label} />
      </div>
      {checked && children ? <div className="param-toggle-row-body">{children}</div> : null}
    </div>
  );
}
