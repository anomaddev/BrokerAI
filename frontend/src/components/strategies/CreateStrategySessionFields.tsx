type CreateStrategySessionFieldsProps = {
  value: string[];
  sessionOptions: readonly string[];
  onChange: (sessions: string[]) => void;
};

export default function CreateStrategySessionFields({
  value,
  sessionOptions,
  onChange,
}: CreateStrategySessionFieldsProps) {
  return (
    <div className="create-strategy-field create-strategy-sessions">
      <div className="strategy-asset-tree-header">
        <span className="param-control-label">Trading sessions</span>
        <span className="strategy-asset-tree-summary">
          {value.length > 0 ? `${value.length} selected` : "None selected"}
        </span>
      </div>
      <p className="settings-muted create-strategy-field-hint">
        Choose when this strategy is allowed to open new trades.
      </p>
      <div className="create-strategy-session-grid">
        {sessionOptions.map((session) => {
          const active = value.includes(session);
          return (
            <button
              key={session}
              type="button"
              className={`create-strategy-session-chip${active ? " create-strategy-session-chip--active" : ""}`}
              aria-pressed={active}
              onClick={() => {
                const next = active ? value.filter((s) => s !== session) : [...value, session];
                onChange(next);
              }}
            >
              {session}
            </button>
          );
        })}
      </div>
      {value.length === 0 && (
        <p className="param-helper param-helper--warn">Select at least one trading session.</p>
      )}
    </div>
  );
}
