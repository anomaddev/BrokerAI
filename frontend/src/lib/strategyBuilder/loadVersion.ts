import type { StrategyVersionSnapshot } from "../../api/client";
import type { StrategyInstrumentSelection } from "../strategies/instruments";
import { emptyInstrumentSelection } from "../strategies/instruments";
import { clampStrategyTitle } from "./components";

/** Normalize snapshot fields for applying into a strategy builder draft. */
export function normalizeVersionSnapshotForBuilder(snapshot: StrategyVersionSnapshot): {
  title: string;
  notes: string;
  instrumentSelection: StrategyInstrumentSelection;
  enabled: boolean;
  params: StrategyVersionSnapshot["params"];
} {
  return {
    title: clampStrategyTitle(snapshot.name || "Untitled strategy"),
    notes: snapshot.description ?? "",
    instrumentSelection: snapshot.instrument_selection ?? emptyInstrumentSelection(),
    enabled: Boolean(snapshot.enabled),
    params: snapshot.params,
  };
}

/** True when the loaded draft differs from the saved baseline dirty snapshot. */
export function isLoadedVersionDirty(
  currentSnapshot: string,
  baselineSnapshot: string,
): boolean {
  return currentSnapshot !== baselineSnapshot;
}
