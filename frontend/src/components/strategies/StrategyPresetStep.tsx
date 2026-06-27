import { STRATEGY_PRESETS } from "../../pages/strategies/presets";

type StrategyPresetStepProps = {
  onSelect: (route: string) => void;
  onBack: () => void;
  onCancel: () => void;
};

export default function StrategyPresetStep({
  onSelect,
  onBack,
  onCancel,
}: StrategyPresetStepProps) {
  return (
    <>
      <button type="button" className="model-form-back" onClick={onBack}>
        ← Back
      </button>
      <h4 className="model-overlay-title" id="create-strategy-preset-title">
        Choose a template
      </h4>
      <p className="model-overlay-desc">
        Select a built-in strategy template to customize and save as your own.
      </p>
      <div className="strategy-preset-list">
        {STRATEGY_PRESETS.map((preset) => {
          const Icon = preset.icon;
          return (
            <button
              key={preset.id}
              type="button"
              className="strategy-preset-card"
              onClick={() => onSelect(preset.route)}
            >
              <div className="strategy-preset-card-header">
                <Icon className="strategy-preset-card-icon" aria-hidden="true" size={20} />
                <span className="model-provider-card-label">{preset.label}</span>
              </div>
              <span className="model-provider-card-desc">{preset.description}</span>
              {preset.tags && preset.tags.length > 0 && (
                <div className="strategy-preset-tags">
                  {preset.tags.map((tag) => (
                    <span key={tag} className="strategy-preset-tag">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </button>
          );
        })}
      </div>
      <div className="confirm-actions">
        <button type="button" className="btn btn-secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </>
  );
}
