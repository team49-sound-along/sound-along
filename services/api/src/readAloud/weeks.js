// Calendar weeks for the "sessions over time" chart. A week is named by its Monday (UTC), "2026-11-02".
const DAY_MS = 86_400_000;

export function weekStart(ms) {
  const d = new Date(ms);
  const sinceMonday = (d.getUTCDay() + 6) % 7;
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() - sinceMonday)).toISOString().slice(0, 10);
}

/** The last `count` weeks ending with the current one, oldest first. */
export function lastWeeks(count, ms) {
  const current = Date.parse(weekStart(ms));
  return Array.from({ length: count }, (_, k) => new Date(current - (count - 1 - k) * 7 * DAY_MS).toISOString().slice(0, 10));
}

export const dayOf = (ms) => new Date(ms).toISOString().slice(0, 10);
