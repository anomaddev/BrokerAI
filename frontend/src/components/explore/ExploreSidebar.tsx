import type { ChartOverlayItem } from "../../lib/chart/chartOverlayState";
import type { Timeframe } from "../../lib/strategyParams";
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
  return (
    <aside className="explore-sidebar" aria-label="Chart analysis">
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
  );
}
