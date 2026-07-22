import { useEffect, useState } from "react";
import type { ChartOverlayItem } from "../../lib/chart/chartOverlayState";
import type { Timeframe } from "../../lib/strategyParams";
import { useIsMobile } from "../../hooks/useMediaQuery";
import ChartOverlayLayerList from "./ChartOverlayLayerList";
import OverlaySearchAutocomplete from "./OverlaySearchAutocomplete";

type ExploreSidebarProps = {
  symbol: string | null;
  chartTimeframe: Timeframe;
  overlayItems: ChartOverlayItem[];
  onOverlayItemsChange: (items: ChartOverlayItem[]) => void;
};

export default function ExploreSidebar({
  symbol,
  chartTimeframe,
  overlayItems,
  onOverlayItemsChange,
}: ExploreSidebarProps) {
  const isMobile = useIsMobile();
  const [sheetOpen, setSheetOpen] = useState(false);

  useEffect(() => {
    if (!isMobile) setSheetOpen(false);
  }, [isMobile]);

  const asideClass = [
    "explore-sidebar",
    "mobile-sheet-panel",
    sheetOpen ? "mobile-sheet-panel--open" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <>
      <aside className={asideClass} aria-label="Chart analysis" aria-hidden={isMobile && !sheetOpen}>
        <div className="mobile-sheet-panel-handle" aria-hidden="true" />
        {isMobile ? (
          <div className="mobile-sheet-panel-toolbar">
            <span className="mobile-sheet-panel-toolbar-label">Overlays</span>
            <button
              type="button"
              className="mobile-sheet-panel-close"
              onClick={() => setSheetOpen(false)}
            >
              Done
            </button>
          </div>
        ) : null}
        <header className="explore-sidebar-header">
          <h2 className="explore-sidebar-title">Analysis</h2>
          <p className="explore-sidebar-desc">
            Add indicators or load an enabled strategy to visualize on the chart.
          </p>
        </header>

        <div className="explore-sidebar-scroll explore-sidebar-scroll--overlays">
          <OverlaySearchAutocomplete
            symbol={symbol}
            chartTimeframe={chartTimeframe}
            overlayItems={overlayItems}
            onOverlayItemsChange={onOverlayItemsChange}
          />

          <ChartOverlayLayerList items={overlayItems} onChange={onOverlayItemsChange} />
        </div>
      </aside>
      {isMobile && !sheetOpen ? (
        <button
          type="button"
          className="mobile-sheet-panel-fab"
          onClick={() => setSheetOpen(true)}
        >
          Overlays
        </button>
      ) : null}
      {isMobile && sheetOpen ? (
        <button
          type="button"
          className="mobile-sheet-scrim"
          aria-label="Close overlays"
          onClick={() => setSheetOpen(false)}
        />
      ) : null}
    </>
  );
}
