/** Placeholder layout while an analysis run page is loading. */
export function AnalysisRunHeaderSkeleton() {
  return (
    <div className="analysis-run-view-title-row analysis-run-view-title-row--skeleton">
      <div className="analysis-run-view-title-block">
        <span className="skeleton analysis-run-skeleton-title" />
        <span className="skeleton analysis-run-skeleton-meta" />
      </div>
      <span className="skeleton analysis-run-skeleton-delete" aria-hidden="true" />
    </div>
  );
}

export function AnalysisRunDetailSkeleton() {
  return (
    <div
      className="analysis-run-detail-layout analysis-run-detail-layout--skeleton"
      aria-busy="true"
      aria-label="Loading analysis run"
    >
      <div className="analysis-run-chart-col">
        <div className="analysis-run-chart-skeleton">
          <span className="skeleton analysis-run-skeleton-chart" />
        </div>
      </div>
      <aside className="analysis-run-panel-col">
        <div className="analysis-run-panel-skeleton">
          <span className="skeleton analysis-run-skeleton-panel-heading" />
          <span className="skeleton analysis-run-skeleton-panel-line" />
          <span className="skeleton analysis-run-skeleton-panel-line analysis-run-skeleton-panel-line--short" />
          <span className="skeleton analysis-run-skeleton-panel-block" />
          <span className="skeleton analysis-run-skeleton-panel-line" />
          <span className="skeleton analysis-run-skeleton-panel-line analysis-run-skeleton-panel-line--short" />
        </div>
      </aside>
    </div>
  );
}
