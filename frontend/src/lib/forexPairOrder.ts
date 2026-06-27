export function splitPairOrder(pairOrder: string[], enabledPairs: string[]) {
  const enabledSet = new Set(enabledPairs);
  const enabled: string[] = [];
  const deactivated: string[] = [];
  for (const pair of pairOrder) {
    if (enabledSet.has(pair)) {
      enabled.push(pair);
    } else {
      deactivated.push(pair);
    }
  }
  return { enabled, deactivated };
}

export function defaultPairOrder(catalog: string[], enabledPairs: string[]): string[] {
  const enabledSet = new Set(enabledPairs);
  const enabled = enabledPairs.filter((p) => catalog.includes(p)).sort((a, b) => a.localeCompare(b));
  const deactivated = catalog.filter((p) => !enabledSet.has(p)).sort((a, b) => a.localeCompare(b));
  return [...enabled, ...deactivated];
}

export function normalizePairOrder(
  catalog: string[],
  enabledPairs: string[],
  pairOrder: string[] | undefined,
): string[] {
  const catalogSet = new Set(catalog);
  const validEnabled = [...new Set(enabledPairs.filter((p) => catalogSet.has(p)))];
  const raw = pairOrder?.length ? pairOrder : defaultPairOrder(catalog, validEnabled);
  const seen = new Set<string>();
  const filtered: string[] = [];
  for (const pair of raw) {
    if (!catalogSet.has(pair) || seen.has(pair)) continue;
    seen.add(pair);
    filtered.push(pair);
  }
  const { enabled, deactivated } = splitPairOrder(filtered, validEnabled);
  const enabledBlock = [...enabled];
  for (const pair of validEnabled) {
    if (!enabledBlock.includes(pair)) {
      enabledBlock.push(pair);
    }
  }
  const disabledBlock = [...deactivated];
  for (const pair of catalog) {
    if (!validEnabled.includes(pair) && !disabledBlock.includes(pair)) {
      disabledBlock.push(pair);
    }
  }
  return [...enabledBlock, ...disabledBlock];
}

export function reorderInSection(
  pairOrder: string[],
  enabledPairs: string[],
  activeId: string,
  overId: string,
  section: "enabled" | "deactivated",
): string[] {
  const { enabled, deactivated } = splitPairOrder(pairOrder, enabledPairs);
  const block = section === "enabled" ? [...enabled] : [...deactivated];
  const oldIndex = block.indexOf(activeId);
  const newIndex = block.indexOf(overId);
  if (oldIndex === -1 || newIndex === -1 || oldIndex === newIndex) {
    return pairOrder;
  }
  block.splice(oldIndex, 1);
  block.splice(newIndex, 0, activeId);
  return section === "enabled" ? [...block, ...deactivated] : [...enabled, ...block];
}

export function enablePair(pairOrder: string[], enabledPairs: string[], pair: string) {
  if (enabledPairs.includes(pair)) {
    return { pairOrder, enabledPairs };
  }
  const newEnabledPairs = [...enabledPairs, pair];
  const { enabled, deactivated } = splitPairOrder(pairOrder, enabledPairs);
  const newEnabledBlock = [...enabled.filter((p) => p !== pair), pair];
  const newDeactivated = deactivated.filter((p) => p !== pair);
  return {
    pairOrder: [...newEnabledBlock, ...newDeactivated],
    enabledPairs: newEnabledPairs,
  };
}

export function disablePair(pairOrder: string[], enabledPairs: string[], pair: string) {
  if (!enabledPairs.includes(pair)) {
    return { pairOrder, enabledPairs };
  }
  const newEnabledPairs = enabledPairs.filter((p) => p !== pair);
  const { enabled, deactivated } = splitPairOrder(pairOrder, enabledPairs);
  const newEnabledBlock = enabled.filter((p) => p !== pair);
  const newDeactivated = [pair, ...deactivated.filter((p) => p !== pair)];
  return {
    pairOrder: [...newEnabledBlock, ...newDeactivated],
    enabledPairs: newEnabledPairs,
  };
}

export function selectAllPairs(catalog: string[], pairOrder: string[], enabledPairs: string[]) {
  const newlyEnabled = catalog.filter((p) => !enabledPairs.includes(p));
  const { enabled, deactivated } = splitPairOrder(pairOrder, enabledPairs);
  const newEnabledBlock = [...enabled, ...newlyEnabled];
  const newDeactivated = deactivated.filter((p) => !catalog.includes(p));
  return {
    pairOrder: [...newEnabledBlock, ...newDeactivated],
    enabledPairs: [...catalog],
  };
}

export function deselectAllPairs(pairOrder: string[], enabledPairs: string[]) {
  const { enabled, deactivated } = splitPairOrder(pairOrder, enabledPairs);
  return {
    pairOrder: [...enabled, ...deactivated],
    enabledPairs: [] as string[],
  };
}
