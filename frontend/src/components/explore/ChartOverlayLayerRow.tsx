import { Eye, EyeOff, X } from "lucide-react";
import type { ChartOverlayItem } from "../../lib/chart/chartOverlayState";
import {
  isAdxSpec,
  overlayIndicatorLabel,
  priceSourceOptions,
} from "../../lib/chart/indicatorCatalog";
import { DIRECTIONS } from "../../lib/strategyParams";
import ColorPickerInput from "./ColorPickerInput";

type ChartOverlayLayerRowProps = {
  item: ChartOverlayItem;
  onUpdate: (patch: Partial<ChartOverlayItem>) => void;
  onRemove: () => void;
};

function OverlayNumberField({
  id,
  label,
  value,
  min,
  max,
  onChange,
}: {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="explore-overlay-param">
      <label htmlFor={id} className="explore-overlay-param-label">
        {label}
      </label>
      <div className="explore-overlay-field-wrap">
        <input
          id={id}
          type="number"
          className="explore-overlay-field"
          min={min}
          max={max}
          step={1}
          value={value}
          onChange={(event) => onChange(Number(event.target.value) || min)}
        />
      </div>
    </div>
  );
}

function OverlaySelectField<T extends string>({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="explore-overlay-param">
      <label htmlFor={id} className="explore-overlay-param-label">
        {label}
      </label>
      <div className="explore-overlay-field-wrap research-select-wrap">
        <select
          id={id}
          className="explore-overlay-field explore-overlay-select"
          value={value}
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

function OverlayColorField({
  id,
  ariaLabel,
  value,
  onChange,
}: {
  id: string;
  ariaLabel: string;
  value: string;
  onChange: (color: string) => void;
}) {
  return (
    <div className="explore-overlay-param explore-overlay-param--color">
      <span className="explore-overlay-param-label explore-overlay-param-label--spacer" aria-hidden="true">
        &#8203;
      </span>
      <div className="explore-overlay-field-wrap explore-overlay-color-field">
        <ColorPickerInput
          id={id}
          variant="param"
          value={value}
          onChange={onChange}
          label={ariaLabel}
        />
      </div>
    </div>
  );
}

export default function ChartOverlayLayerRow({
  item,
  onUpdate,
  onRemove,
}: ChartOverlayLayerRowProps) {
  const rowClass = `explore-overlay-row${item.visible ? "" : " explore-overlay-row--hidden"}`;

  if (item.overlayKind === "signals") {
    return (
      <div className={rowClass}>
        <div className="explore-overlay-row-main">
          <button
            type="button"
            className="explore-overlay-icon-btn explore-overlay-visibility"
            aria-label={item.visible ? "Hide overlay" : "Show overlay"}
            onClick={() => onUpdate({ visible: !item.visible })}
          >
            {item.visible ? <Eye size={14} /> : <EyeOff size={14} />}
          </button>

          <div className="explore-overlay-row-info">
            <span className="explore-overlay-row-name">EMA Crossover Signals</span>
            <span className="explore-overlay-row-subtitle">{item.source.strategyName}</span>
          </div>

          <button
            type="button"
            className="explore-overlay-icon-btn explore-overlay-remove"
            aria-label="Remove overlay"
            onClick={onRemove}
          >
            <X size={14} />
          </button>
        </div>

        <div className="explore-overlay-row-params explore-overlay-row-params--signals">
          <OverlaySelectField
            id={`${item.id}-direction`}
            label="Direction"
            value={item.direction}
            options={DIRECTIONS.map((direction) => ({ value: direction, label: direction }))}
            onChange={(direction) => onUpdate({ direction })}
          />
          <OverlayNumberField
            id={`${item.id}-confidence`}
            label="Min confidence"
            value={item.minConfidence}
            min={0}
            max={100}
            onChange={(minConfidence) => onUpdate({ minConfidence })}
          />
        </div>
      </div>
    );
  }

  const ref = item.source.kind === "strategy" ? item.source.ref : undefined;
  const name = overlayIndicatorLabel(item.spec, ref);
  const subtitle =
    item.source.kind === "strategy" ? item.source.strategyName : undefined;

  return (
    <div className={rowClass}>
      <div className="explore-overlay-row-main">
        <button
          type="button"
          className="explore-overlay-icon-btn explore-overlay-visibility"
          aria-label={item.visible ? "Hide overlay" : "Show overlay"}
          onClick={() => onUpdate({ visible: !item.visible })}
        >
          {item.visible ? <Eye size={14} /> : <EyeOff size={14} />}
        </button>

        <div className="explore-overlay-row-info">
          <span className="explore-overlay-row-name">{name}</span>
          {subtitle ? <span className="explore-overlay-row-subtitle">{subtitle}</span> : null}
        </div>

        <button
          type="button"
          className="explore-overlay-icon-btn explore-overlay-remove"
          aria-label="Remove overlay"
          onClick={onRemove}
        >
          <X size={14} />
        </button>
      </div>

      <div
        className={`explore-overlay-row-params${
          isAdxSpec(item.spec) ? " explore-overlay-row-params--compact" : ""
        }`}
      >
        <OverlayColorField
          id={`${item.id}-color`}
          ariaLabel={`${name} color`}
          value={item.color}
          onChange={(color) => onUpdate({ color })}
        />

        <OverlayNumberField
          id={`${item.id}-period`}
          label="Period"
          value={item.spec.period}
          min={1}
          max={500}
          onChange={(period) => onUpdate({ spec: { ...item.spec, period } })}
        />

        {!isAdxSpec(item.spec) ? (
          <OverlaySelectField
            id={`${item.id}-source`}
            label="Source"
            value={item.spec.source ?? "close"}
            options={priceSourceOptions()}
            onChange={(source) => onUpdate({ spec: { ...item.spec, source } })}
          />
        ) : null}
      </div>
    </div>
  );
}
