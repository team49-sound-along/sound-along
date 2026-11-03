// Pure formatting helpers. Missing or invalid values render as an em dash, never as invented data.
export const DASH = "—";

const isNum = (n) => typeof n === "number" && Number.isFinite(n);

/** 125000 ms -> "2:05". */
export function formatDuration(ms) {
  if (!isNum(ms) || ms < 0) return DASH;
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function formatCount(n) {
  return isNum(n) ? n.toLocaleString("en-US") : DASH;
}

/** Small amounts keep 4 decimals so a $0.0031 cost is not shown as $0.00. */
export function formatUsd(n) {
  if (!isNum(n)) return DASH;
  const digits = n >= 100 ? 0 : n >= 1 ? 2 : 4;
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

export function formatPercent(n, digits = 1) {
  return isNum(n) ? `${n.toFixed(digits)}%` : DASH;
}

export function formatMinutes(n) {
  return isNum(n) ? `${n.toLocaleString("en-US", { maximumFractionDigits: 1 })} min` : DASH;
}

/** Real-time factor: seconds of work per second of audio, shown as "0.12x". */
export function formatRtf(n) {
  return isNum(n) ? `${n.toFixed(2)}×` : DASH;
}

export function formatMs(n) {
  return isNum(n) ? `${Math.round(n).toLocaleString("en-US")} ms` : DASH;
}

/** A 0..1 share as a whole-number percent ("0.884" -> "88%"). */
export function formatShare(n) {
  return isNum(n) ? `${Math.round(n * 100)}%` : DASH;
}

/** Predicted MOS score to one decimal ("4.51" -> "4.5"). */
export function formatMos(n) {
  return isNum(n) ? n.toFixed(1) : DASH;
}

export function formatSeconds(n) {
  return isNum(n) ? `${n.toFixed(1)} s` : DASH;
}

/** Share of `part` in `total` as a percentage number, or null when undefined. */
export function percentOf(part, total) {
  return isNum(part) && isNum(total) && total > 0 ? (part / total) * 100 : null;
}

/** "2026-03-04" or ISO timestamp -> "Mar 4, 2026". Date-only strings avoid timezone shifts. */
export function formatDate(value) {
  if (typeof value !== "string" || !value) return DASH;
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const d = dateOnly ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3])) : new Date(value);
  if (Number.isNaN(d.getTime())) return DASH;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function titleCase(value) {
  return typeof value === "string" && value ? value[0].toUpperCase() + value.slice(1) : DASH;
}
