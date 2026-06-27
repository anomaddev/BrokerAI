export function formatUptime(durationMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000));
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

export function uptimeMsSince(isoTimestamp: string | null | undefined, now = Date.now()): number | null {
  if (!isoTimestamp) return null;
  const started = new Date(isoTimestamp).getTime();
  if (Number.isNaN(started)) return null;
  return Math.max(0, now - started);
}
