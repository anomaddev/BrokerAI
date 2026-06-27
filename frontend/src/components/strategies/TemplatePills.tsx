import type { StrategyTemplatePill } from "../../lib/strategies/types";

const MAX_PILLS = 5;

type TemplatePillsProps = {
  items: StrategyTemplatePill[];
};

export default function TemplatePills({ items }: TemplatePillsProps) {
  if (items.length === 0) return null;

  const visible = items.slice(0, MAX_PILLS);
  const remaining = items.length - MAX_PILLS;

  return (
    <div className="strategy-template-pills">
      {visible.map((item) => (
        <span
          key={`${item.assetClass}-${item.label}`}
          className={`strategy-template-pill strategy-template-pill--${item.assetClass}`}
        >
          {item.label}
        </span>
      ))}
      {remaining > 0 && (
        <span className="strategy-template-pill strategy-template-pill--more">
          +{remaining} more
        </span>
      )}
    </div>
  );
}
