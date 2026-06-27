type ChartOverlayToggleProps = {
  label: string;
  active: boolean;
  disabled?: boolean;
  onChange: (active: boolean) => void;
};

export default function ChartOverlayToggle({
  label,
  active,
  disabled = false,
  onChange,
}: ChartOverlayToggleProps) {
  return (
    <button
      type="button"
      className={`chart-overlay-toggle${active ? " chart-overlay-toggle--active" : ""}${
        disabled ? " chart-overlay-toggle--disabled" : ""
      }`}
      aria-pressed={active}
      disabled={disabled}
      onClick={() => onChange(!active)}
    >
      {label}
    </button>
  );
}
