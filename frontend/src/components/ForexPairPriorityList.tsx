import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  type DragEndEvent,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical } from "lucide-react";
import ToggleSwitch from "./ToggleSwitch";
import {
  disablePair,
  enablePair,
  reorderInSection,
  splitPairOrder,
} from "../lib/forexPairOrder";

type ForexPairPriorityListProps = {
  pairOrder: string[];
  enabledPairs: string[];
  onPairOrderChange: (pairOrder: string[]) => void;
  onEnabledPairsChange: (enabledPairs: string[]) => void;
  onReorder: () => void;
  onToggle: () => void;
};

type SortableRowProps = {
  pair: string;
  enabled: boolean;
  onToggle: (pair: string, next: boolean) => void;
};

function SortableRow({ pair, enabled, onToggle }: SortableRowProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: pair,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`forex-pair-priority-row${isDragging ? " forex-pair-priority-row--dragging" : ""}`}
    >
      <button
        type="button"
        className="forex-pair-drag-handle"
        aria-label={`Drag to reorder ${pair}`}
        {...attributes}
        {...listeners}
      >
        <GripVertical size={16} aria-hidden="true" />
      </button>
      <span className="forex-pair-label">{pair}</span>
      <ToggleSwitch
        label={`${enabled ? "Disable" : "Enable"} ${pair}`}
        checked={enabled}
        onChange={(next) => onToggle(pair, next)}
      />
    </div>
  );
}

type PairSectionProps = {
  title: string;
  pairs: string[];
  enabled: boolean;
  emptyMessage: string;
  onDragEnd: (event: DragEndEvent) => void;
  onToggle: (pair: string, next: boolean) => void;
};

function PairSection({
  title,
  pairs,
  enabled,
  emptyMessage,
  onDragEnd,
  onToggle,
}: PairSectionProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  return (
    <section className="forex-pair-priority-section">
      <h4 className="forex-pair-priority-section-title">{title}</h4>
      {pairs.length === 0 ? (
        <p className="settings-muted forex-pair-priority-empty">{emptyMessage}</p>
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          <SortableContext items={pairs} strategy={verticalListSortingStrategy}>
            <div className="forex-pair-priority-list">
              {pairs.map((pair) => (
                <SortableRow key={pair} pair={pair} enabled={enabled} onToggle={onToggle} />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}
    </section>
  );
}

export default function ForexPairPriorityList({
  pairOrder,
  enabledPairs,
  onPairOrderChange,
  onEnabledPairsChange,
  onReorder,
  onToggle,
}: ForexPairPriorityListProps) {
  const { enabled, deactivated } = splitPairOrder(pairOrder, enabledPairs);

  function handleToggle(pair: string, next: boolean) {
    if (next) {
      const result = enablePair(pairOrder, enabledPairs, pair);
      onPairOrderChange(result.pairOrder);
      onEnabledPairsChange(result.enabledPairs);
    } else {
      const result = disablePair(pairOrder, enabledPairs, pair);
      onPairOrderChange(result.pairOrder);
      onEnabledPairsChange(result.enabledPairs);
    }
    onToggle();
  }

  function handleDragEnd(section: "enabled" | "deactivated") {
    return (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || active.id === over.id) return;
      const next = reorderInSection(
        pairOrder,
        enabledPairs,
        String(active.id),
        String(over.id),
        section,
      );
      onPairOrderChange(next);
      onReorder();
    };
  }

  return (
    <div className="forex-pair-priority">
      <PairSection
        title="Enabled pairs"
        pairs={enabled}
        enabled
        emptyMessage="No pairs enabled. Toggle pairs on below to activate them for analysis and trading."
        onDragEnd={handleDragEnd("enabled")}
        onToggle={handleToggle}
      />
      <PairSection
        title="Deactivated pairs"
        pairs={deactivated}
        enabled={false}
        emptyMessage="All catalog pairs are enabled."
        onDragEnd={handleDragEnd("deactivated")}
        onToggle={handleToggle}
      />
    </div>
  );
}
