type StrategyModeStepProps = {
  onSelectPreset: () => void;
  onCancel: () => void;
};

export default function StrategyModeStep({ onSelectPreset, onCancel }: StrategyModeStepProps) {
  return (
    <>
      <h4 className="model-overlay-title" id="create-strategy-title">
        Create strategy
      </h4>
      <p className="model-overlay-desc">Choose how you want to set up your strategy.</p>
      <div className="model-provider-grid">
        <button type="button" className="model-provider-card" onClick={onSelectPreset}>
          <span className="model-provider-card-label">Template</span>
          <span className="model-provider-card-desc">
            Start from a built-in strategy template you can tweak and save.
          </span>
        </button>
        <button type="button" className="model-provider-card" disabled>
          <span className="model-provider-card-label">Custom</span>
          <span className="model-provider-card-desc">Build your own strategy from scratch.</span>
          <span className="exchange-coming-soon">Coming soon</span>
        </button>
      </div>
      <div className="confirm-actions">
        <button type="button" className="btn btn-secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </>
  );
}
