import { ChevronDown } from "lucide-react";

type ParameterCardProps = {
  title: string;
  badge?: string;
  required?: boolean;
  expanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
};

export default function ParameterCard({
  title,
  badge,
  required = false,
  expanded,
  onToggle,
  children,
}: ParameterCardProps) {
  return (
    <section className={`parameter-card${expanded ? " parameter-card--expanded" : ""}`}>
      <button
        type="button"
        className="parameter-card-header"
        onClick={onToggle}
        aria-expanded={expanded}
      >
        <span className="parameter-card-title">{title}</span>
        {required || badge ? (
          <span className="parameter-card-badges">
            {required ? (
              <span className="parameter-card-badge parameter-card-badge--required">Required</span>
            ) : null}
            {badge ? <span className="parameter-card-badge">{badge}</span> : null}
          </span>
        ) : null}
        <ChevronDown className="parameter-card-chevron" aria-hidden="true" size={16} />
      </button>
      <div className="parameter-card-body">{children}</div>
    </section>
  );
}
