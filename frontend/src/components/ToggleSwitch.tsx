type ToggleSwitchProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  label: string;
};

export default function ToggleSwitch({ checked, onChange, disabled, label }: ToggleSwitchProps) {
  return (
    <label className="toggle-switch" title={label}>
      <input
        type="checkbox"
        className="toggle-switch-input"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        aria-label={label}
      />
      <span className="toggle-switch-track" aria-hidden="true" />
    </label>
  );
}
