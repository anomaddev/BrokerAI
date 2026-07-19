import { Link2, Plus, Unlink, X } from "lucide-react";
import ColorPickerInput from "../../explore/ColorPickerInput";
import {
  EMA_PERIOD_MAX,
  EMA_PERIOD_MIN,
  MAX_SIGNALS,
  addAdditionalTimeframes,
  addEmaComponent,
  addSignalComponent,
  canAddSignal,
  emaLabel,
  getAdditionalTimeframes,
  getEmaComponents,
  getPrimaryTimeframe,
  getSignalComponents,
  hasAdditionalTimeframes,
  hasSignal,
  isEmaPeriodTaken,
  nextAvailableEmaPeriod,
  removeComponent,
  updateComponent,
  updateEmaColor,
  updateEmaPeriod,
  updateSignalJoin,
  type StrategyBuilderComponent,
} from "../../../lib/strategyBuilder/components";
import {
  MIN_CANDLES_SLIDER_MAX,
  MIN_CANDLES_SLIDER_MIN,
  TIMEFRAME_OPTIONS,
  TIMEFRAME_LABELS,
  formatCandleLookback,
  type Confirmation,
  type Direction,
  type Timeframe,
} from "../../../lib/strategyParams";
import {
  SIGNAL_CATALOG_SECTIONS,
  findIndicatorCatalogEntry,
  findSignalCatalogEntry,
  type SignalCatalogType,
} from "../../../lib/strategyParams/catalog";
import LiveSlider from "../params/LiveSlider";
import NumberStepper from "../params/NumberStepper";
import SegmentedControl from "../params/SegmentedControl";
import TimeframeSelect from "../params/TimeframeSelect";
import ParamHelpTip from "../params/ParamHelpTip";

const EMA_INDICATOR_HELP = findIndicatorCatalogEntry("ema");

const SIGNAL_JOIN_HELP = {
  label: "Signal combination",
  title: "AND / OR & chain links",
  body: "AND requires both sides; OR accepts either. The chain link groups signals like parentheses: linked signals form one group, and an unlinked break starts a new group. Example: S1 linked S2 unlinked S3 is (S1 AND/OR S2) AND/OR S3.",
} as const;

type StrategyComponentsPanelProps = {
  components: StrategyBuilderComponent[];
  computedMinCandles: number;
  onChange: (components: StrategyBuilderComponent[]) => void;
  /** When true, signal type is locked (EMA Crossover template). */
  signalLocked?: boolean;
};

export default function StrategyComponentsPanel({
  components,
  computedMinCandles,
  onChange,
  signalLocked = false,
}: StrategyComponentsPanelProps) {
  const primary = getPrimaryTimeframe(components);
  const additional = getAdditionalTimeframes(components);
  const emas = getEmaComponents(components);
  const signals = getSignalComponents(components);
  const canAddEma = nextAvailableEmaPeriod(components) != null;
  const belowComputedMin = Boolean(primary && primary.minCandles < computedMinCandles);
  const outOfRange = Boolean(
    primary &&
      (primary.minCandles < MIN_CANDLES_SLIDER_MIN || primary.minCandles > MIN_CANDLES_SLIDER_MAX),
  );
  const minInvalid =
    !primary || outOfRange || belowComputedMin || computedMinCandles > MIN_CANDLES_SLIDER_MAX;

  function toggleAdditionalTimeframe(tf: Timeframe) {
    if (!additional) return;
    const next = additional.timeframes.includes(tf)
      ? additional.timeframes.filter((item) => item !== tf)
      : [...additional.timeframes, tf];
    onChange(updateComponent(components, additional.id, { timeframes: next }));
  }

  const primaryTf = primary?.timeframe;
  const additionalOptions = TIMEFRAME_OPTIONS.filter((option) => option.value !== primaryTf);

  return (
    <div className="strategy-components-panel">
      <section className="strategy-component-section">
        <div className="strategy-component-section-header">
          <h3 className="strategy-component-section-title">Timeframes</h3>
          {!hasAdditionalTimeframes(components) ? (
            <button
              type="button"
              className="strategy-component-add-btn"
              onClick={() => onChange(addAdditionalTimeframes(components))}
            >
              <Plus size={14} aria-hidden />
              Additional Timeframes
            </button>
          ) : null}
        </div>

        {primary ? (
          <div className="strategy-component-card">
            <div className="strategy-component-card-header">
              <span className="strategy-component-card-title">Timeframe</span>
              <span className="strategy-component-badge">Required</span>
            </div>
            <TimeframeSelect
              value={primary.timeframe}
              options={TIMEFRAME_OPTIONS}
              onChange={(value) => {
                const next = updateComponent(components, primary.id, { timeframe: value });
                const add = getAdditionalTimeframes(next);
                if (add?.timeframes.includes(value)) {
                  onChange(
                    updateComponent(next, add.id, {
                      timeframes: add.timeframes.filter((tf) => tf !== value),
                    }),
                  );
                  return;
                }
                onChange(next);
              }}
            />
            <LiveSlider
              id="min-candles"
              label="Minimum candles required"
              value={primary.minCandles}
              min={MIN_CANDLES_SLIDER_MIN}
              max={MIN_CANDLES_SLIDER_MAX}
              step={10}
              invalid={minInvalid}
              onChange={(value) =>
                onChange(updateComponent(components, primary.id, { minCandles: value }))
              }
            />
            {computedMinCandles > MIN_CANDLES_SLIDER_MAX ? (
              <p className="param-helper param-helper--warn">
                Computed minimum ({computedMinCandles}) exceeds the maximum allowed (
                {MIN_CANDLES_SLIDER_MAX}). Reduce indicator or filter periods.
              </p>
            ) : belowComputedMin ? (
              <p className="param-helper param-helper--warn">
                Must be at least {computedMinCandles} bars for this strategy&apos;s indicators and
                filters.
              </p>
            ) : outOfRange ? (
              <p className="param-helper param-helper--warn">
                Must be between {MIN_CANDLES_SLIDER_MIN} and {MIN_CANDLES_SLIDER_MAX} bars.
              </p>
            ) : (
              <p className="param-helper">
                Bars needed before the strategy can run on the next candle (
                {MIN_CANDLES_SLIDER_MIN}–{MIN_CANDLES_SLIDER_MAX}).
              </p>
            )}
            {primary.minCandles > 0 ? (
              <p className="param-helper">
                About {formatCandleLookback(primary.timeframe, primary.minCandles)} at{" "}
                {TIMEFRAME_LABELS[primary.timeframe]}.
              </p>
            ) : null}
          </div>
        ) : null}

        {additional ? (
          <div className="strategy-component-card">
            <div className="strategy-component-card-header">
              <span className="strategy-component-card-title">Additional Timeframes</span>
              <button
                type="button"
                className="strategy-component-remove-btn"
                onClick={() => onChange(removeComponent(components, additional.id))}
                aria-label="Remove additional timeframes"
              >
                <X size={14} />
              </button>
            </div>
            <div className="strategy-tf-multiselect" role="group" aria-label="Additional timeframes">
              {additionalOptions.map((option) => {
                const selected = additional.timeframes.includes(option.value);
                return (
                  <button
                    key={option.value}
                    type="button"
                    className={`strategy-tf-chip${selected ? " strategy-tf-chip--selected" : ""}`}
                    aria-pressed={selected}
                    onClick={() => toggleAdditionalTimeframe(option.value)}
                  >
                    {TIMEFRAME_LABELS[option.value]}
                  </button>
                );
              })}
            </div>
            <p className="param-helper">Select extra candle timeframes to fetch with this strategy.</p>
          </div>
        ) : null}
      </section>

      <section className="strategy-component-section">
        <div className="strategy-component-section-header">
          <h3 className="strategy-component-section-title">Indicators</h3>
          <button
            type="button"
            className="strategy-component-add-btn"
            disabled={!canAddEma}
            onClick={() => onChange(addEmaComponent(components))}
            title={canAddEma ? undefined : "All EMA periods are already in use"}
          >
            <Plus size={14} aria-hidden />
            EMA
          </button>
        </div>

        {emas.length === 0 ? (
          <p className="settings-muted strategy-component-empty">
            No indicators yet. Add an EMA to get started.
          </p>
        ) : (
          emas.map((ema) => {
            const periodTaken = isEmaPeriodTaken(components, ema.period, ema.id);
            const title = emaLabel(ema.period);
            return (
              <div
                key={ema.id}
                data-ema-id={ema.id}
                className={`strategy-component-card strategy-component-card--row${
                  periodTaken ? " strategy-component-card--error" : ""
                }`}
              >
                <div className="strategy-component-card-header">
                  <div className="strategy-component-card-title-row">
                    <ColorPickerInput
                      id={`ema-color-${ema.id}`}
                      label={`${title} color`}
                      value={ema.color}
                      variant="param"
                      onChange={(color) => onChange(updateEmaColor(components, ema.id, color))}
                    />
                    <span className="strategy-component-card-title">{title}</span>
                    {EMA_INDICATOR_HELP ? (
                      <ParamHelpTip
                        label={title}
                        title={EMA_INDICATOR_HELP.label}
                        body={EMA_INDICATOR_HELP.description}
                      />
                    ) : null}
                  </div>
                  <div className="strategy-component-card-header-actions">
                    {periodTaken ? (
                      <span className="strategy-component-error" role="alert">
                        Already exists
                      </span>
                    ) : null}
                    <button
                      type="button"
                      className="strategy-component-remove-btn"
                      onClick={() => onChange(removeComponent(components, ema.id))}
                      aria-label={`Remove ${title}`}
                    >
                      <X size={14} />
                    </button>
                  </div>
                </div>
                <div className="strategy-component-ema-fields">
                  <NumberStepper
                    id={`ema-period-${ema.id}`}
                    label="Period"
                    value={ema.period}
                    min={EMA_PERIOD_MIN}
                    max={EMA_PERIOD_MAX}
                    showButtons
                    invalid={periodTaken}
                    onChange={(value) => onChange(updateEmaPeriod(components, ema.id, value))}
                  />
                </div>
              </div>
            );
          })
        )}
      </section>

      <section className="strategy-component-section">
        <div className="strategy-component-section-header">
          <h3 className="strategy-component-section-title">Signals</h3>
          {!hasSignal(components) ? (
            <button
              type="button"
              className="strategy-component-add-btn"
              onClick={() => onChange(addSignalComponent(components))}
            >
              <Plus size={14} aria-hidden />
              Signal
            </button>
          ) : null}
        </div>

        {signals.length === 0 ? (
          <p className="settings-muted strategy-component-empty">
            No signal yet. Add a signal to define entries.
          </p>
        ) : (
          <>
            {signals.map((signal, index) => {
              const signalEntry = signal.signalType
                ? findSignalCatalogEntry(signal.signalType)
                : undefined;
              const isCrossover = signal.signalType === "ema_crossover";
              const crossoverNeedsEmas = isCrossover && emas.length < 2;
              const crossoverSameEma =
                isCrossover &&
                Boolean(signal.fastEmaId) &&
                signal.fastEmaId === signal.slowEmaId;
              const isPrimary = index === 0;
              const typeLocked = signalLocked && isPrimary;
              const title = isPrimary ? "Signal" : `Signal ${index + 1}`;
              const nextSignal = signals[index + 1];
              const isLast = index === signals.length - 1;

              return (
                <div key={signal.id} className="strategy-signal-block">
                  <div className="strategy-component-card">
                    <div className="strategy-component-card-header">
                      <span className="strategy-component-card-title">{title}</span>
                      <div className="strategy-component-card-header-actions">
                        {typeLocked ? (
                          <span className="strategy-component-badge">Required</span>
                        ) : (
                          <button
                            type="button"
                            className="strategy-component-remove-btn"
                            onClick={() => onChange(removeComponent(components, signal.id))}
                            aria-label={`Remove ${title}`}
                          >
                            <X size={14} />
                          </button>
                        )}
                      </div>
                    </div>

                    {typeLocked && signalEntry ? (
                      <div className="param-control param-control--readonly">
                        <span className="param-control-label">
                          Signal type
                          <span className="param-control-required">Required</span>
                        </span>
                        <span className="param-control-value param-control-value--locked">
                          {signalEntry.label}
                        </span>
                      </div>
                    ) : (
                      <div className="param-control">
                        <label
                          htmlFor={`strategy-signal-type-${signal.id}`}
                          className="param-control-label"
                        >
                          Signal type
                          <span className="param-control-required">Required</span>
                        </label>
                        <div className="research-select-wrap">
                          <select
                            id={`strategy-signal-type-${signal.id}`}
                            className="research-select"
                            value={signal.signalType}
                            onChange={(event) =>
                              onChange(
                                updateComponent(components, signal.id, {
                                  signalType: event.target.value as SignalCatalogType | "",
                                }),
                              )
                            }
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
                      </div>
                    )}

                    {signalEntry ? <p className="param-helper">{signalEntry.description}</p> : null}

                    {isCrossover ? (
                      <div className="strategy-crossover-ema-fields">
                        <div className="param-control">
                          <label
                            htmlFor={`crossover-fast-ema-${signal.id}`}
                            className="param-control-label"
                          >
                            Fast EMA
                            <span className="param-control-required">Required</span>
                          </label>
                          <div className="research-select-wrap">
                            <select
                              id={`crossover-fast-ema-${signal.id}`}
                              className="research-select"
                              value={signal.fastEmaId ?? ""}
                              disabled={emas.length < 1}
                              onChange={(event) =>
                                onChange(
                                  updateComponent(components, signal.id, {
                                    fastEmaId: event.target.value || undefined,
                                  }),
                                )
                              }
                            >
                              <option value="">Select EMA…</option>
                              {emas.map((ema) => (
                                <option key={ema.id} value={ema.id}>
                                  {emaLabel(ema.period)}
                                </option>
                              ))}
                            </select>
                          </div>
                        </div>

                        <div className="param-control">
                          <label
                            htmlFor={`crossover-slow-ema-${signal.id}`}
                            className="param-control-label"
                          >
                            Slow EMA
                            <span className="param-control-required">Required</span>
                          </label>
                          <div className="research-select-wrap">
                            <select
                              id={`crossover-slow-ema-${signal.id}`}
                              className="research-select"
                              value={signal.slowEmaId ?? ""}
                              disabled={emas.length < 2}
                              onChange={(event) =>
                                onChange(
                                  updateComponent(components, signal.id, {
                                    slowEmaId: event.target.value || undefined,
                                  }),
                                )
                              }
                            >
                              <option value="">Select EMA…</option>
                              {emas.map((ema) => (
                                <option
                                  key={ema.id}
                                  value={ema.id}
                                  disabled={ema.id === signal.fastEmaId}
                                >
                                  {emaLabel(ema.period)}
                                </option>
                              ))}
                            </select>
                          </div>
                        </div>

                        {crossoverNeedsEmas ? (
                          <p className="param-helper param-helper--warn">
                            Add at least two EMA indicators to configure the crossover.
                          </p>
                        ) : null}
                        {crossoverSameEma ? (
                          <p className="param-helper param-helper--warn">
                            Fast and slow must use different EMA indicators.
                          </p>
                        ) : null}
                      </div>
                    ) : null}

                    <div className="strategy-signal-rules">
                      <SegmentedControl
                        label="Direction"
                        value={signal.direction}
                        labelHelp={
                          <ParamHelpTip
                            label="Direction"
                            title="Direction"
                            body="Choose which sides this strategy may trade: Long only, Short only, or Both."
                          />
                        }
                        options={[
                          { value: "long", label: "Long" },
                          { value: "short", label: "Short" },
                          { value: "both", label: "Both" },
                        ]}
                        onChange={(value) =>
                          onChange(
                            updateComponent(components, signal.id, {
                              direction: value as Direction,
                            }),
                          )
                        }
                      />
                      <SegmentedControl
                        label="Confirmation"
                        value={signal.confirmation}
                        labelHelp={
                          <ParamHelpTip
                            label="Confirmation"
                            title="Confirmation"
                            body="Sets entry timing after a signal: Close waits for the candle to close, Pullback waits for a retest, and Aggressive enters as soon as the signal forms."
                          />
                        }
                        options={[
                          { value: "close", label: "Close" },
                          { value: "pullback", label: "Pullback" },
                          { value: "aggressive", label: "Aggressive" },
                        ]}
                        onChange={(value) =>
                          onChange(
                            updateComponent(components, signal.id, {
                              confirmation: value as Confirmation,
                            }),
                          )
                        }
                      />
                    </div>
                  </div>

                  {nextSignal ? (
                    <div
                      className="strategy-signal-separator strategy-signal-separator--join"
                      role="group"
                      aria-label={`Combine Signal ${index + 1} with Signal ${index + 2}`}
                    >
                      <span className="strategy-signal-separator-help">
                        <ParamHelpTip
                          label={SIGNAL_JOIN_HELP.label}
                          title={SIGNAL_JOIN_HELP.title}
                          body={SIGNAL_JOIN_HELP.body}
                        />
                      </span>
                      <span className="strategy-signal-separator-line" aria-hidden />
                      <div
                        className="strategy-signal-combine"
                        role="tablist"
                        aria-label="Combine with"
                      >
                        {(
                          [
                            { value: "and", label: "AND" },
                            { value: "or", label: "OR" },
                          ] as const
                        ).map((option) => {
                          const active = (nextSignal.combineWithPrevious ?? "and") === option.value;
                          return (
                            <button
                              key={option.value}
                              type="button"
                              role="tab"
                              aria-selected={active}
                              className={`strategy-signal-combine-btn${
                                active ? " strategy-signal-combine-btn--active" : ""
                              }`}
                              onClick={() =>
                                onChange(
                                  updateSignalJoin(components, nextSignal.id, {
                                    combineWithPrevious: option.value,
                                  }),
                                )
                              }
                            >
                              {option.label}
                            </button>
                          );
                        })}
                      </div>
                      <span className="strategy-signal-separator-line" aria-hidden />
                      <button
                        type="button"
                        className={`strategy-signal-chain-btn${
                          nextSignal.linkedWithPrevious !== false
                            ? " strategy-signal-chain-btn--linked"
                            : ""
                        }`}
                        aria-pressed={nextSignal.linkedWithPrevious !== false}
                        aria-label={
                          nextSignal.linkedWithPrevious !== false
                            ? "Unlink signals (break parenthesis group)"
                            : "Link signals (group with parenthesis)"
                        }
                        title={
                          nextSignal.linkedWithPrevious !== false
                            ? "Linked — grouped in parentheses"
                            : "Unlinked — separate group"
                        }
                        onClick={() =>
                          onChange(
                            updateSignalJoin(components, nextSignal.id, {
                              linkedWithPrevious: nextSignal.linkedWithPrevious === false,
                            }),
                          )
                        }
                      >
                        {nextSignal.linkedWithPrevious !== false ? (
                          <Link2 size={14} aria-hidden />
                        ) : (
                          <Unlink size={14} aria-hidden />
                        )}
                      </button>
                    </div>
                  ) : null}

                  {isLast && canAddSignal(components) ? (
                    <div
                      className="strategy-signal-separator"
                      role="group"
                      aria-label="Add another signal"
                    >
                      <button
                        type="button"
                        className="strategy-signal-separator-add"
                        onClick={() => onChange(addSignalComponent(components))}
                      >
                        <Plus size={14} aria-hidden />
                        Add signal
                      </button>
                    </div>
                  ) : null}

                  {isLast && signals.length >= MAX_SIGNALS ? (
                    <p className="param-helper strategy-signal-max-hint">
                      Maximum of {MAX_SIGNALS} signals.
                    </p>
                  ) : null}
                </div>
              );
            })}
          </>
        )}
      </section>
    </div>
  );
}
