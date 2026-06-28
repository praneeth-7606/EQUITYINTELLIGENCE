export function formatInr(value: number): string {
  const abs = Math.abs(value);
  const formatted = new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(abs);
  return (value < 0 ? '-' : '') + '₹' + formatted;
}

export function formatPct(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return sign + value.toFixed(2) + '%';
}

export function parseNumericValue(str: string): number {
  if (!str) return 0;
  const cleaned = str.replace(/[₹,%+\s]/g, '');
  return parseFloat(cleaned) || 0;
}
