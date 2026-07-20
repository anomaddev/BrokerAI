import { useMemo, useState } from "react";
import type { BacktestPeriod, Strategy } from "../../api/client";
import ToggleSwitch from "../ToggleSwitch";
import StrategyOverlay from "./StrategyOverlay";

export const DEFAULT_ACCOUNT_MARGIN = 10_000;
export const MIN_ACCOUNT_MARGIN = 100;
export const MAX_ACCOUNT_MARGIN = 50_000_000;

export type QueueBacktestParams = {
  name?: string;
  instrument: string;
  period: BacktestPeriod;
  verbose: boolean;
  account_margin: number;
};

type QueueBacktestOverlayProps = {
  strategies: Strategy[];
  submitting?: boolean;
  error?: string | null;
  onClose: () => void;
  onConfirm: (params: QueueBacktestParams) => void | Promise<void>;
};

const PERIOD_OPTIONS: Array<{ value: BacktestPeriod; label: string }> = [
  { value: "1m", label: "1 month" },
  { value: "3m", label: "3 months" },
  { value: "6m", label: "6 months" },
  { value: "1y", label: "1 year" },
  { value: "2y", label: "2 years" },
  { value: "5y", label: "5 years" },
];

function uniqueInstruments(strategies: Strategy[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const strategy of strategies) {
    for (const raw of strategy.instruments ?? []) {
      const symbol = String(raw || "").trim();
      if (!symbol || seen.has(symbol)) continue;
      seen.add(symbol);
      out.push(symbol);
    }
  }
  return out.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
}

export default function QueueBacktestOverlay({
  strategies,
  submitting = false,
  error = null,
  onClose,
  onConfirm,
}: QueueBacktestOverlayProps) {
  const instruments = useMemo(() => uniqueInstruments(strategies), [strategies]);
  const [name, setName] = useState("");
  const [instrument, setInstrument] = useState(() => instruments[0] ?? "");
  const [period, setPeriod] = useState<BacktestPeriod>("6m");
  const [accountMargin, setAccountMargin] = useState(String(DEFAULT_ACCOUNT_MARGIN));
  const [verbose, setVerbose] = useState(false);

  const strategyCount = strategies.length;
  const strategyLabel =
    strategyCount === 1
      ? strategies[0]?.name || "1 strategy"
      : `${strategyCount} strategies`;

  const parsedMargin = Number(accountMargin);
  const marginValid =
    Number.isFinite(parsedMargin) &&
    parsedMargin >= MIN_ACCOUNT_MARGIN &&
    parsedMargin <= MAX_ACCOUNT_MARGIN;
  const canSubmit =
    Boolean(instrument) && !submitting && instruments.length > 0 && marginValid;

  async function handleSubmit() {
    if (!canSubmit) return;
    await onConfirm({
      name: name.trim() || undefined,
      instrument,
      period,
      verbose,
      account_margin: parsedMargin,
    });
  }

  return (
    <StrategyOverlay onClose={onClose} wide titleId="queue-backtest-title">
      <div className="model-overlay-body">
        <h4 className="model-overlay-title" id="queue-backtest-title">
          Queue backtest
        </h4>
        <p className="model-overlay-desc">
          Set the historical window and instrument for{" "}
          <strong>{strategyLabel}</strong>. Each selected strategy gets its own queued run.
        </p>

        <div className="settings-form model-overlay-form">
          <div className="param-control">
            <label htmlFor="queue-backtest-name" className="param-control-label">
              Name
              <span className="param-control-optional">Optional</span>
            </label>
            <input
              id="queue-backtest-name"
              type="text"
              maxLength={120}
              placeholder="e.g. EUR/USD 6m baseline"
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={submitting}
            />
          </div>

          <div className="param-control">
            <label htmlFor="queue-backtest-instrument" className="param-control-label">
              Instrument
              <span className="param-control-required">Required</span>
            </label>
            {instruments.length === 0 ? (
              <p className="param-helper param-helper--warn">
                Selected strategies have no specific instruments assigned. Edit a strategy and
                pick at least one symbol before queueing a backtest.
              </p>
            ) : (
              <div className="research-select-wrap">
                <select
                  id="queue-backtest-instrument"
                  className="research-select"
                  value={instrument}
                  onChange={(event) => setInstrument(event.target.value)}
                  disabled={submitting}
                >
                  {instruments.map((symbol) => (
                    <option key={symbol} value={symbol}>
                      {symbol}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          <div className="param-control">
            <label htmlFor="queue-backtest-period" className="param-control-label">
              Historical period
              <span className="param-control-required">Required</span>
            </label>
            <div className="research-select-wrap">
              <select
                id="queue-backtest-period"
                className="research-select"
                value={period}
                onChange={(event) => setPeriod(event.target.value as BacktestPeriod)}
                disabled={submitting}
              >
                {PERIOD_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="param-control">
            <label htmlFor="queue-backtest-margin" className="param-control-label">
              Available account margin
              <span className="param-control-required">Required</span>
            </label>
            <div className="model-overlay-currency-input">
              <span className="model-overlay-currency-prefix" aria-hidden="true">
                $
              </span>
              <input
                id="queue-backtest-margin"
                type="number"
                min={MIN_ACCOUNT_MARGIN}
                max={MAX_ACCOUNT_MARGIN}
                step="100"
                value={accountMargin}
                onChange={(event) => setAccountMargin(event.target.value)}
                disabled={submitting}
                aria-label="Available account margin in USD"
              />
            </div>
            <p className="param-helper">
              Starting USD balance used for position sizing (min $100, max $50,000,000).
            </p>
            {!marginValid && accountMargin.trim() !== "" ? (
              <p className="param-helper param-helper--warn">
                Enter a value between ${MIN_ACCOUNT_MARGIN.toLocaleString()} and $
                {MAX_ACCOUNT_MARGIN.toLocaleString()}.
              </p>
            ) : null}
          </div>

          <div className="research-source-row model-overlay-toggle">
            <div className="research-source-main">
              <span className="research-source-name">Verbose logs</span>
              <span className="settings-muted">
                Include DEBUG lines while the backtest runs.
              </span>
            </div>
            <ToggleSwitch
              label="Verbose logs"
              checked={verbose}
              disabled={submitting}
              onChange={setVerbose}
            />
          </div>
        </div>
      </div>

      <div className="model-overlay-footer">
        {error ? <p className="settings-error model-overlay-feedback">{error}</p> : null}
        <div className="confirm-actions model-overlay-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
            disabled={submitting}
          >
            Cancel
          </button>
          <div className="model-overlay-actions-primary">
            <button
              type="button"
              className="btn"
              onClick={() => void handleSubmit()}
              disabled={!canSubmit}
            >
              {submitting ? "Queueing…" : "Queue backtest"}
            </button>
          </div>
        </div>
      </div>
    </StrategyOverlay>
  );
}
