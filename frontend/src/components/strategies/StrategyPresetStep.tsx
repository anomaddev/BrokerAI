import { getBuildStrategyPresets } from "../../pages/strategies/presets";

type StrategyPresetStepProps = {
  onSelect: (route: string) => void;
  onCancel: () => void;
};

export default function StrategyPresetStep({ onSelect, onCancel }: StrategyPresetStepProps) {
  const presets = getBuildStrategyPresets();

  return (
    <>
      <h4 className="model-overlay-title" id="create-strategy-preset-title">
        Build Strategy
      </h4>
      <p className="model-overlay-desc">
        Start from a built-in template. Templates are read-only starters — your saved strategy is
        always a new copy you can edit freely.
      </p>
      <div className="strategy-preset-list">
        {presets.map((preset) => {
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
