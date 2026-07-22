import { useEffect, useState } from "react";

type ToggleSwitchProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  label: string;
};

/**
 * Controlled switch with local optimistic paint so the thumb moves on the same
 * click frame even if the parent re-render is deferred behind a slow autosave.
 */
export default function ToggleSwitch({ checked, onChange, disabled, label }: ToggleSwitchProps) {
  const [displayChecked, setDisplayChecked] = useState(checked);

  useEffect(() => {
    setDisplayChecked(checked);
  }, [checked]);

  return (
    <label className="toggle-switch" title={label}>
      <input
        type="checkbox"
        className="toggle-switch-input"
        checked={displayChecked}
        disabled={disabled}
        onChange={(e) => {
          const next = e.target.checked;
          setDisplayChecked(next);
          onChange(next);
        }}
        aria-label={label}
      />
      <span className="toggle-switch-track" aria-hidden="true" />
    </label>
  );
}
