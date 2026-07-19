import type { StrategyInstrumentSelection } from "../strategies/instruments";
import type { StrategyBuilderComponent } from "./components";

/** Snapshot of persistable builder state for dirty checks (excludes chart UI toggles). */
export function strategyBuilderDirtySnapshot(input: {
  title: string;
  notes: string;
  instrumentSelection: StrategyInstrumentSelection;
  components: StrategyBuilderComponent[];
  params: Record<string, unknown>;
}): string {
  const { overlays: _overlays, overlayMode: _overlayMode, ...persistableParams } = input.params;
  return JSON.stringify({
    title: input.title,
    notes: input.notes,
    instrumentSelection: input.instrumentSelection,
    components: input.components,
    params: persistableParams,
  });
}
