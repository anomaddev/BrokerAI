import type { ChartOverlayItem } from "../../lib/chart/chartOverlayState";
import { removeOverlayItem, updateOverlayItem } from "../../lib/chart/chartOverlayState";
import ChartOverlayLayerRow from "./ChartOverlayLayerRow";

type ChartOverlayLayerListProps = {
  items: ChartOverlayItem[];
  onChange: (items: ChartOverlayItem[]) => void;
};

export default function ChartOverlayLayerList({ items, onChange }: ChartOverlayLayerListProps) {
  if (items.length === 0) {
    return (
      <p className="explore-sidebar-empty">
        Add an indicator or strategy to overlay on the chart.
      </p>
    );
  }

  return (
    <ul className="explore-overlay-list">
      {items.map((item) => (
        <li key={item.id}>
          <ChartOverlayLayerRow
            item={item}
            onUpdate={(patch) => onChange(updateOverlayItem(items, item.id, patch))}
            onRemove={() => onChange(removeOverlayItem(items, item.id))}
          />
        </li>
      ))}
    </ul>
  );
}
