import type { CSSProperties } from "react";

type DashboardSkeletonProps = {
  cards?: number;
  layout?: "grid" | "oanda-row";
};

function SkeletonBlock({
  className = "",
  style,
}: {
  className?: string;
  style?: CSSProperties;
}) {
  return <span className={`skeleton ${className}`.trim()} style={style} aria-hidden="true" />;
}

export function DashboardSummarySkeleton() {
  return (
    <div className="dashboard-summary dashboard-summary--skeleton" aria-hidden="true">
      <div className="dashboard-stats">
        {Array.from({ length: 6 }, (_, index) => (
          <div className="dashboard-stat" key={index}>
            <SkeletonBlock className="skeleton--label" />
            <SkeletonBlock className="skeleton--value" />
          </div>
        ))}
      </div>
      <SkeletonBlock className="skeleton--line skeleton--line-short" />
    </div>
  );
}

function DashboardCardSkeleton() {
  return (
    <article className="dashboard-card dashboard-card--skeleton" aria-hidden="true">
      <div className="dashboard-card-head">
        <SkeletonBlock className="skeleton--logo" />
        <div className="dashboard-card-title">
          <SkeletonBlock className="skeleton--title" />
          <SkeletonBlock className="skeleton--subtitle" />
        </div>
        <SkeletonBlock className="skeleton--badge" />
      </div>

      <SkeletonBlock className="skeleton--line" />

      <DashboardSummarySkeleton />

      <div className="dashboard-card-footer">
        <SkeletonBlock className="skeleton--footer-label" />
        <div className="dashboard-skeleton-tags">
          <SkeletonBlock className="skeleton--tag" />
          <SkeletonBlock className="skeleton--tag skeleton--tag-wide" />
        </div>
      </div>
    </article>
  );
}

function DashboardRecentTradesSkeleton() {
  return (
    <section
      className="dashboard-recent-trades dashboard-card--skeleton"
      aria-hidden="true"
    >
      <div className="dashboard-recent-trades-head">
        <SkeletonBlock className="skeleton--title" style={{ width: "8rem" }} />
        <SkeletonBlock className="skeleton--line-short" style={{ width: "4rem" }} />
      </div>
      <div className="dashboard-recent-trades-skeleton">
        {Array.from({ length: 6 }, (_, index) => (
          <div className="dashboard-recent-trades-skeleton-row" key={index}>
            <SkeletonBlock className="skeleton--value" />
            <SkeletonBlock className="skeleton--value" />
            <SkeletonBlock className="skeleton--value" />
            <SkeletonBlock className="skeleton--value" />
            <SkeletonBlock className="skeleton--value" />
            <SkeletonBlock className="skeleton--value" />
            <SkeletonBlock className="skeleton--value" />
          </div>
        ))}
      </div>
    </section>
  );
}

export default function DashboardSkeleton({
  cards = 2,
  layout = "grid",
}: DashboardSkeletonProps) {
  if (layout === "oanda-row") {
    return (
      <div
        className="dashboard-oanda-row dashboard-grid--loading"
        aria-busy="true"
        aria-label="Loading dashboard"
      >
        <DashboardCardSkeleton />
        <DashboardRecentTradesSkeleton />
      </div>
    );
  }

  return (
    <div className="dashboard-grid dashboard-grid--loading" aria-busy="true" aria-label="Loading dashboard">
      {Array.from({ length: cards }, (_, index) => (
        <DashboardCardSkeleton key={index} />
      ))}
    </div>
  );
}
