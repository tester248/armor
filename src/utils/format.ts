/** Formatting helpers shared by the telemetry screens. */

export function num(value: unknown, digits = 1, fallback = '--'): string {
  const n = typeof value === 'number' ? value : Number(value);
  if (value === null || value === undefined || Number.isNaN(n)) return fallback;
  return n.toFixed(digits);
}

export function int(value: unknown, fallback = '--'): string {
  const n = typeof value === 'number' ? value : Number(value);
  if (value === null || value === undefined || Number.isNaN(n)) return fallback;
  return String(Math.round(n));
}

/** "2026-10-28T18:59:40.123Z" → "18:59:40" (falls back to the raw tail). */
export function clock(ts?: string | null): string {
  if (!ts) return '--:--:--';
  const m = /T(\d{2}:\d{2}:\d{2})/.exec(ts);
  if (m) return m[1];
  return ts.slice(-8);
}

/** "2026-10-28T18:59:40Z" → "28 Oct · 18:59" */
export function stamp(ts?: string | null): string {
  if (!ts) return '--';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts.slice(0, 16).replace('T', ' ');
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${d.getDate()} ${months[d.getMonth()]} · ${hh}:${mm}`;
}

export function ago(ts?: string | null): string {
  if (!ts) return 'no data';
  const d = new Date(ts).getTime();
  if (Number.isNaN(d)) return 'no data';
  const s = Math.max(0, Math.round((Date.now() - d) / 1000));
  if (s < 2) return 'just now';
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  return `${Math.round(s / 3600)}h ago`;
}

export function pct(value: unknown, digits = 0): string {
  const n = typeof value === 'number' ? value : Number(value);
  if (value === null || value === undefined || Number.isNaN(n)) return '--';
  return `${(n * 100).toFixed(digits)}%`;
}
