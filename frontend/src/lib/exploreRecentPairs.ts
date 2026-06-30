const STORAGE_KEY = "brokerai.explore.recent";
const MAX_RECENT = 8;

export type RecentPair = {
  symbol: string;
  viewedAt: string;
};

function readRaw(): RecentPair[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (item): item is RecentPair =>
          typeof item === "object" &&
          item !== null &&
          typeof (item as RecentPair).symbol === "string" &&
          typeof (item as RecentPair).viewedAt === "string",
      )
      .slice(0, MAX_RECENT);
  } catch {
    return [];
  }
}

function writeRaw(items: RecentPair[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, MAX_RECENT)));
}

export function loadRecentPairs(): RecentPair[] {
  return readRaw();
}

export function recordRecentPair(symbol: string): RecentPair[] {
  const now = new Date().toISOString();
  const next = [{ symbol, viewedAt: now }, ...readRaw().filter((item) => item.symbol !== symbol)].slice(
    0,
    MAX_RECENT,
  );
  writeRaw(next);
  return next;
}

export function buildOrderedPairSuggestions(
  catalog: string[],
  enabledPairs: string[],
  pairOrder: string[],
): string[] {
  const catalogSet = new Set(catalog);
  const orderedEnabled = (pairOrder.length ? pairOrder : enabledPairs).filter(
    (pair) => catalogSet.has(pair) && enabledPairs.includes(pair),
  );
  const enabledSet = new Set(orderedEnabled);
  const remaining = catalog.filter((pair) => !enabledSet.has(pair));
  return [...orderedEnabled, ...remaining];
}

export function pairMatchesQuery(pair: string, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const normalized = pair.toLowerCase();
  const compact = normalized.replace("/", "");
  const compactQuery = q.replace("/", "");
  return normalized.includes(q) || compact.includes(compactQuery);
}
