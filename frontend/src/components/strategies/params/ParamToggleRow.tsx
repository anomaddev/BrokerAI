import ToggleSwitch from "../../ToggleSwitch";

type ParamToggleRowProps = {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  children?: React.ReactNode;
};

export default function ParamToggleRow({
  label,
  checked,
  onChange,
  children,
}: ParamToggleRowProps) {
  return (
    <div className="param-toggle-row">
      <div className="param-toggle-row-header">
        <span className="param-control-label">{label}</span>
        <ToggleSwitch checked={checked} onChange={onChange} label={label} />
      </div>
      {checked && children ? <div className="param-toggle-row-body">{children}</div> : null}
    </div>
  );
}
