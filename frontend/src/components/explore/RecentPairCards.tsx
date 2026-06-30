import type { RecentPair } from "../../lib/exploreRecentPairs";

type RecentPairCardsProps = {
  items: RecentPair[];
  selectedSymbol: string | null;
  onSelect: (symbol: string) => void;
};

export default function RecentPairCards({
  items,
  selectedSymbol,
  onSelect,
}: RecentPairCardsProps) {
  if (items.length === 0) return null;

  return (
    <div className="explore-recent-strip" role="list" aria-label="Recently viewed pairs">
      {items.map((item) => {
        const active = item.symbol === selectedSymbol;
        return (
          <button
            key={item.symbol}
            type="button"
            role="listitem"
            className={`explore-recent-chip${active ? " explore-recent-chip--active" : ""}`}
            onClick={() => onSelect(item.symbol)}
          >
            {item.symbol}
          </button>
        );
      })}
    </div>
  );
}
