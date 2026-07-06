import type { AnalysisRunRecency } from "../../lib/analysis/analysisRunRecency";

type AnalysisRecencyBadgeProps = {
  recency: AnalysisRunRecency;
};

export default function AnalysisRecencyBadge({ recency }: AnalysisRecencyBadgeProps) {
  if (recency === "historical") return null;

  return (
    <span
      className={`analysis-recency-badge analysis-recency-badge--${recency}`}
    >
      {recency === "current" ? "Current" : "Stale"}
    </span>
  );
}
