import { useNavigate } from "react-router-dom";
import { STRATEGY_PRESETS } from "../../pages/strategies/presets";
import TemplatePills from "./TemplatePills";

export default function StrategyTemplatesSection() {
  const navigate = useNavigate();

  return (
    <section className="strategy-templates-section" aria-labelledby="strategy-templates-title">
      <header className="strategy-templates-header">
        <h2 className="settings-subtitle" id="strategy-templates-title">
          Templates
        </h2>
        <p className="strategy-templates-lead">
          Get started with built-in, tweakable strategies. Pick a template, adjust parameters, and
          save it as your own.
        </p>
      </header>

      <div className="strategy-templates-grid">
        {STRATEGY_PRESETS.map((template) => {
          const Icon = template.icon;
          return (
            <button
              key={template.id}
              type="button"
              className="strategy-template-card"
              onClick={() => navigate(template.route)}
            >
              <div className="strategy-template-card-head">
                <span className="strategy-template-card-icon-wrap" aria-hidden="true">
                  <Icon className="strategy-template-card-icon" size={20} />
                </span>
                <div className="strategy-template-card-copy">
                  <span className="strategy-template-card-label">{template.label}</span>
                  <span className="strategy-template-card-desc">{template.description}</span>
                </div>
              </div>
              <TemplatePills items={template.enabledPills} />
            </button>
          );
        })}
      </div>
    </section>
  );
}
