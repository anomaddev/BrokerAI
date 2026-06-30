export function formatChartPrice(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1000) return value.toFixed(2);
  if (abs >= 100) return value.toFixed(3);
  if (abs >= 10) return value.toFixed(4);
  if (abs >= 1) return value.toFixed(5);
  return value.toFixed(6);
}
