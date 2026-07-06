type Props = {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  disabled?: boolean;
  onChange: (value: number) => void;
};

export default function RetentionStepper({
  id,
  label,
  value,
  min,
  max,
  step,
  disabled = false,
  onChange,
}: Props) {
  const canDecrease = value > min;
  const canIncrease = value < max;

  function adjust(delta: number) {
    const next = Math.min(max, Math.max(min, value + delta));
    if (next !== value) onChange(next);
  }

  return (
    <div className="research-field research-schedule-field backup-retention-field">
      <label className="research-field-label" htmlFor={id}>
        {label}
      </label>
      <div
        className={`backup-retention-stepper${disabled ? " backup-retention-stepper--disabled" : ""}`}
      >
        <button
          type="button"
          className="backup-retention-stepper-btn"
          disabled={disabled || !canDecrease}
          aria-label={`Decrease ${label}`}
          onClick={() => adjust(-step)}
        >
          −
        </button>
        <span id={id} className="backup-retention-stepper-value" aria-live="polite">
          {value}
        </span>
        <button
          type="button"
          className="backup-retention-stepper-btn"
          disabled={disabled || !canIncrease}
          aria-label={`Increase ${label}`}
          onClick={() => adjust(step)}
        >
          +
        </button>
      </div>
      <p className="settings-muted backup-retention-range">
        {min}–{max} entries
      </p>
    </div>
  );
}
