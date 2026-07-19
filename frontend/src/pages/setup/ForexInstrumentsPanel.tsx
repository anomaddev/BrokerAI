import { disablePair, enablePair } from "../../lib/forexPairOrder";

type ForexInstrumentsPanelProps = {
  enabledPairs: string[];
  pairOrder: string[];
  catalog: string[];
  onEnabledPairsChange: (pairs: string[]) => void;
  onPairOrderChange: (order: string[]) => void;
  disabled?: boolean;
};

export default function ForexInstrumentsPanel({
  enabledPairs,
  pairOrder,
  catalog,
  onEnabledPairsChange,
  onPairOrderChange,
  disabled = false,
}: ForexInstrumentsPanelProps) {
  const enabledSet = new Set(enabledPairs);
  // Stable A→Z order so the 4-column grid fills left→right, then next row.
  const pairs = [...catalog].sort((a, b) => a.localeCompare(b));
  const orderBase = pairOrder.length > 0 ? pairOrder : pairs;

  function handleToggle(pair: string, next: boolean) {
    if (next) {
      const result = enablePair(orderBase, enabledPairs, pair);
      onPairOrderChange(result.pairOrder);
      onEnabledPairsChange(result.enabledPairs);
      return;
    }
    const result = disablePair(orderBase, enabledPairs, pair);
    onPairOrderChange(result.pairOrder);
    onEnabledPairsChange(result.enabledPairs);
  }

  return (
    <div className={`onboarding-instruments${disabled ? " onboarding-instruments--disabled" : ""}`}>
      <div className="onboarding-instruments-grid" role="group" aria-label="Forex instruments">
        {pairs.map((pair) => {
          const checked = enabledSet.has(pair);
          return (
            <label
              key={pair}
              className={`onboarding-instrument-chip${checked ? " is-selected" : ""}`}
            >
              <input
                type="checkbox"
                checked={checked}
                disabled={disabled}
                onChange={(e) => handleToggle(pair, e.target.checked)}
              />
              <span>{pair}</span>
            </label>
          );
        })}
      </div>
    </div>
  );
}
