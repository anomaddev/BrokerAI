import ParameterCard from "../ParameterCard";
import LiveSlider from "../LiveSlider";
import ParamReadOnlyRow from "../ParamReadOnlyRow";
import {
  findSignalCatalogEntry,
  SIGNAL_CATALOG_SECTIONS,
  type SignalCatalogType,
} from "../../../../lib/strategyParams/catalog";

type SignalSectionProps = {
  expanded: boolean;
  onToggle: () => void;
  signalType: SignalCatalogType | "";
  onSignalTypeChange?: (value: SignalCatalogType | "") => void;
  locked?: boolean;
  /** When true, EMA periods are managed elsewhere (Indicators components). */
  hideEmaFields?: boolean;
  fastEma: number;
  slowEma: number;
  onFastEmaChange: (value: number) => void;
  onSlowEmaChange: (value: number) => void;
};

export default function SignalSection({
  expanded,
  onToggle,
  signalType,
  onSignalTypeChange,
  locked = false,
  hideEmaFields = false,
  fastEma,
  slowEma,
  onFastEmaChange,
  onSlowEmaChange,
}: SignalSectionProps) {
  const emaInvalid = signalType === "ema_crossover" && fastEma >= slowEma;
  const showEmaFields = signalType === "ema_crossover" && !hideEmaFields;
  const selectedEntry = signalType ? findSignalCatalogEntry(signalType) : undefined;

  return (
    <ParameterCard
      title="Signal"
      required
      expanded={expanded}
      onToggle={onToggle}
      badge={!signalType || emaInvalid ? "!" : undefined}
    >
      {locked && selectedEntry ? (
        <ParamReadOnlyRow
          id="signal-type"
          label="Signal type"
          value={selectedEntry.label}
          required
        />
      ) : (
        <div className="param-control">
          <label htmlFor="signal-type" className="param-control-label">
            Signal type
            <span className="param-control-required">Required</span>
          </label>
          <div className="research-select-wrap">
            <select
              id="signal-type"
              className="research-select"
              value={signalType}
              onChange={(event) => onSignalTypeChange?.(event.target.value as SignalCatalogType | "")}
            >
              <option value="">Select a signal…</option>
              {SIGNAL_CATALOG_SECTIONS.map((section) => (
                <optgroup key={section.id} label={section.label}>
                  {section.signals.map((item) => (
                    <option key={item.type} value={item.type}>
                      {item.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          {!signalType && (
            <p className="param-helper">Choose an entry signal to configure your strategy.</p>
          )}
        </div>
      )}

      {selectedEntry && !showEmaFields && (
        <p className="param-helper">{selectedEntry.description}</p>
      )}

      {showEmaFields && (
        <>
          <LiveSlider
            id="fast-ema"
            label="Fast EMA period"
            value={fastEma}
            min={3}
            max={50}
            onChange={onFastEmaChange}
          />
          <LiveSlider
            id="slow-ema"
            label="Slow EMA period"
            value={slowEma}
            min={10}
            max={200}
            invalid={emaInvalid}
            onChange={onSlowEmaChange}
          />
          {emaInvalid && (
            <p className="param-helper param-helper--warn">Fast must be less than slow EMA.</p>
          )}
        </>
      )}
    </ParameterCard>
  );
}
