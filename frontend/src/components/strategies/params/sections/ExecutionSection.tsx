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
  dontHoldBetweenSessions: boolean;
  dontHoldBetweenMarkets: boolean;
  closeBeforeMarketHours: number;
  noLateMarketTrading: boolean;
  lateMarketHours: number;
  onMinConfidenceChange: (value: number) => void;
  onMaxTradesChange: (value: number) => void;
  onOverrideChange: (value: boolean) => void;
  onDontHoldBetweenSessionsChange: (value: boolean) => void;
  onDontHoldBetweenMarketsChange: (value: boolean) => void;
  onCloseBeforeMarketHoursChange: (value: number) => void;
  onNoLateMarketTradingChange: (value: boolean) => void;
  onLateMarketHoursChange: (value: number) => void;
  postStopCooldownBars?: number;
  onPostStopCooldownBarsChange?: (value: number) => void;
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
  dontHoldBetweenSessions: {
    label: "Don't hold between sessions",
    title: "Don't hold between sessions",
    body: "When on, close open trades one candle before leaving an enabled session island (Sydney, Asia, London, NY). Overlaps keep the trade if another enabled session is still open. Uses sessions enabled both globally and on this strategy.",
  },
  dontHoldBetweenMarkets: {
    label: "Don't hold between markets",
    title: "Don't hold between markets",
    body: "When on, close open trades before major market closes (weekends and holidays), not the daily FX break. Close time respects enabled sessions (for example, London-only ends earlier Friday than NY).",
  },
  closeBeforeMarketHours: {
    label: "Close hours before market close",
    title: "Close hours before market close",
    body: "How many hours before that major market close to flatten open trades (1–24). Only applies when Don't Hold Between Markets is on.",
  },
  noLateMarketTrading: {
    label: "No late market trading",
    title: "No late market trading",
    body: "When on, block new entries near major market close (weekends and holidays), using the same session-aware close as Don't Hold Between Markets.",
  },
  lateMarketHours: {
    label: "Late market hours",
    title: "No new trades within hours of market close",
    body: "How many hours before major market close to stop opening new trades (1–24). Only applies when No Late Market Trading is on.",
  },
  postStopCooldown: {
    label: "Cooldown after stop-loss",
    title: "Cooldown bars after stop-loss",
    body: "After a stop-loss exit, wait this many bars before allowing a new entry on the same symbol. Reduces flip-flop clusters. 0 disables.",
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
  dontHoldBetweenSessions,
  dontHoldBetweenMarkets,
  closeBeforeMarketHours,
  noLateMarketTrading,
  lateMarketHours,
  onMinConfidenceChange,
  onMaxTradesChange,
  onOverrideChange,
  onDontHoldBetweenSessionsChange,
  onDontHoldBetweenMarketsChange,
  onCloseBeforeMarketHoursChange,
  onNoLateMarketTradingChange,
  onLateMarketHoursChange,
  postStopCooldownBars = 0,
  onPostStopCooldownBarsChange,
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
      <ParamToggleRow
        label="Don't Hold Between Sessions"
        checked={dontHoldBetweenSessions}
        labelHelp={
          <ParamHelpTip
            label={EXECUTION_HELP.dontHoldBetweenSessions.label}
            title={EXECUTION_HELP.dontHoldBetweenSessions.title}
            body={EXECUTION_HELP.dontHoldBetweenSessions.body}
          />
        }
        onChange={onDontHoldBetweenSessionsChange}
      />
      <ParamToggleRow
        label="Don't Hold Between Markets"
        checked={dontHoldBetweenMarkets}
        labelHelp={
          <ParamHelpTip
            label={EXECUTION_HELP.dontHoldBetweenMarkets.label}
            title={EXECUTION_HELP.dontHoldBetweenMarkets.title}
            body={EXECUTION_HELP.dontHoldBetweenMarkets.body}
          />
        }
        onChange={onDontHoldBetweenMarketsChange}
      >
        <LiveSlider
          id="close-before-market-hours"
          label="Close trades hours before market close"
          labelHelp={
            <ParamHelpTip
              label={EXECUTION_HELP.closeBeforeMarketHours.label}
              title={EXECUTION_HELP.closeBeforeMarketHours.title}
              body={EXECUTION_HELP.closeBeforeMarketHours.body}
            />
          }
          value={closeBeforeMarketHours}
          min={1}
          max={24}
          unit="h"
          onChange={onCloseBeforeMarketHoursChange}
        />
      </ParamToggleRow>
      <ParamToggleRow
        label="No Late Market Trading"
        checked={noLateMarketTrading}
        labelHelp={
          <ParamHelpTip
            label={EXECUTION_HELP.noLateMarketTrading.label}
            title={EXECUTION_HELP.noLateMarketTrading.title}
            body={EXECUTION_HELP.noLateMarketTrading.body}
          />
        }
        onChange={onNoLateMarketTradingChange}
      >
        <LiveSlider
          id="late-market-hours"
          label="No new trades within hours of market close"
          labelHelp={
            <ParamHelpTip
              label={EXECUTION_HELP.lateMarketHours.label}
              title={EXECUTION_HELP.lateMarketHours.title}
              body={EXECUTION_HELP.lateMarketHours.body}
            />
          }
          value={lateMarketHours}
          min={1}
          max={24}
          unit="h"
          onChange={onLateMarketHoursChange}
        />
      </ParamToggleRow>
      {onPostStopCooldownBarsChange && (
        <NumberStepper
          id="post-stop-cooldown"
          label="Cooldown bars after stop-loss"
          labelHelp={
            <ParamHelpTip
              label={EXECUTION_HELP.postStopCooldown.label}
              title={EXECUTION_HELP.postStopCooldown.title}
              body={EXECUTION_HELP.postStopCooldown.body}
            />
          }
          value={postStopCooldownBars}
          min={0}
          max={30}
          onChange={onPostStopCooldownBarsChange}
        />
      )}
    </ParameterCard>
  );
}
