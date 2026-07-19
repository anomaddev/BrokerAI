import ParameterCard from "../ParameterCard";
import LiveSlider from "../LiveSlider";
import NumberStepper from "../NumberStepper";
import ParamToggleRow from "../ParamToggleRow";
import ParamHelpTip from "../ParamHelpTip";
import { MARKET_SESSION_DEFS } from "../../../../lib/marketSessionDefs";

type ExecutionSectionProps = {
  expanded: boolean;
  onToggle: () => void;
  sessions: string[];
  onSessionsChange: (sessions: string[]) => void;
  minConfidence: number;
  maxTradesPerDay: number;
  overrideAllStrategies: boolean;
  onMinConfidenceChange: (value: number) => void;
  onMaxTradesChange: (value: number) => void;
  onOverrideChange: (value: boolean) => void;
};

const EXECUTION_HELP = {
  sessions: {
    label: "Trading sessions",
    title: "Trading sessions",
    body: "Choose which market sessions this strategy may open new trades in. Any combination of Sydney, Asia, London, and NY is allowed.",
  },
  minConfidence: {
    label: "Min confidence threshold",
    title: "Min confidence threshold",
    body: "Signals below this confidence score are ignored. Higher values mean fewer, higher-conviction trades.",
  },
  maxTrades: {
    label: "Max trades per day",
    title: "Max trades per day, per symbol",
    body: "Caps how many new trades this strategy can open on a single symbol in one trading day.",
  },
  override: {
    label: "Override all other strategies",
    title: "Override all other strategies",
    body: "When enabled, this strategy’s signals take precedence over conflicting signals from other strategies on the same instrument.",
  },
} as const;

export default function ExecutionSection({
  expanded,
  onToggle,
  sessions,
  onSessionsChange,
  minConfidence,
  maxTradesPerDay,
  overrideAllStrategies,
  onMinConfidenceChange,
  onMaxTradesChange,
  onOverrideChange,
}: ExecutionSectionProps) {
  return (
    <ParameterCard
      className="parameter-card--execution"
      title="Execution"
      required
      expanded={expanded}
      onToggle={onToggle}
      badge={sessions.length === 0 ? "!" : undefined}
    >
      <div className="param-control">
        <div className="param-control-label-row">
          <div className="param-control-label-with-help">
            <span className="param-control-label">
              Trading sessions
              <span className="param-control-required">Required</span>
            </span>
            <ParamHelpTip
              label={EXECUTION_HELP.sessions.label}
              title={EXECUTION_HELP.sessions.title}
              body={EXECUTION_HELP.sessions.body}
            />
          </div>
        </div>
        <div className="strategy-markets-grid" role="group" aria-label="Trading sessions">
          {MARKET_SESSION_DEFS.map((session) => {
            const selected = sessions.includes(session.name);
            return (
              <button
                key={session.id}
                type="button"
                className={`strategy-market-chip${
                  selected ? " strategy-market-chip--selected" : ""
                }`}
                aria-pressed={selected}
                title={session.hours}
                onClick={() => {
                  const next = selected
                    ? sessions.filter((name) => name !== session.name)
                    : [...sessions, session.name];
                  onSessionsChange(next);
                }}
              >
                <span className="strategy-market-chip-label">{session.name}</span>
                <span className="strategy-market-chip-hours">{session.hours}</span>
              </button>
            );
          })}
        </div>
        {sessions.length === 0 ? (
          <p className="param-helper param-helper--warn">Select at least one trading session.</p>
        ) : (
          <p className="param-helper">Choose when this strategy may open new trades.</p>
        )}
      </div>

      <LiveSlider
        id="min-confidence"
        label="Min confidence threshold"
        labelHelp={
          <ParamHelpTip
            label={EXECUTION_HELP.minConfidence.label}
            title={EXECUTION_HELP.minConfidence.title}
            body={EXECUTION_HELP.minConfidence.body}
          />
        }
        value={minConfidence}
        min={0}
        max={100}
        unit="%"
        onChange={onMinConfidenceChange}
      />
      <NumberStepper
        id="max-trades"
        label="Max trades per day, per symbol"
        labelHelp={
          <ParamHelpTip
            label={EXECUTION_HELP.maxTrades.label}
            title={EXECUTION_HELP.maxTrades.title}
            body={EXECUTION_HELP.maxTrades.body}
          />
        }
        value={maxTradesPerDay}
        min={1}
        max={20}
        showButtons
        onChange={onMaxTradesChange}
      />
      <ParamToggleRow
        label="Override all other strategies"
        checked={overrideAllStrategies}
        labelHelp={
          <ParamHelpTip
            label={EXECUTION_HELP.override.label}
            title={EXECUTION_HELP.override.title}
            body={EXECUTION_HELP.override.body}
          />
        }
        onChange={onOverrideChange}
      />
    </ParameterCard>
  );
}
