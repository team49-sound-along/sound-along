// Pure shaping of numbers into chart geometry for the hand-written SVG charts. No DOM, no Vue. Missing values are never drawn as zero.

/** A round upper bound for a scale: 7 -> 10, 14 -> 15, 22 -> 25, 0 -> 1. */
export function niceMax(max) {
  if (!Number.isFinite(max) || max <= 0) return 1;
  const steps = [1, 2, 3, 4, 5, 10, 15, 20, 25, 30, 40, 50, 75, 100];
  const hit = steps.find((s) => s >= max);
  if (hit) return hit;
  const mag = 10 ** Math.floor(Math.log10(max));
  return Math.ceil(max / mag) * mag;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "2026-11-02" -> "Nov 2" */
export function dayLabel(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso));
  return m ? `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}` : "";
}

/**
 * Points for a line over equally spaced steps. `values` may hold null (no data): such a step has no point and breaks the line.
 * Returns { points: [{ x, y, value, label }], segments: [[point...]], max }.
 */
export function linePoints(values, labels, { width, height, left = 36, right = 12, top = 12, bottom = 28, max } = {}) {
  const top$ = niceMax(max ?? Math.max(0, ...values.filter((v) => v !== null)));
  const innerW = width - left - right;
  const innerH = height - top - bottom;
  const step = values.length > 1 ? innerW / (values.length - 1) : 0;
  const points = values.map((value, i) => ({
    x: left + (values.length > 1 ? i * step : innerW / 2),
    y: value === null ? null : top + innerH - (value / top$) * innerH,
    value,
    label: labels[i] ?? "",
  }));
  const segments = points.reduce((acc, p) => {
    if (p.value === null) return [...acc, []];
    const last = acc.length ? acc[acc.length - 1] : null;
    return last ? [...acc.slice(0, -1), [...last, p]] : [[p]];
  }, []).filter((s) => s.length > 0);
  return { points, segments, max: top$, baseline: top + innerH, left, right: width - right };
}

export const pathOf = (segment) => segment.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
export const areaOf = (segment, baseline) => (segment.length < 2 ? "" : `${pathOf(segment)} L${segment.at(-1).x.toFixed(1)} ${baseline} L${segment[0].x.toFixed(1)} ${baseline} Z`);

/** Horizontal bar rows: width as a share of `max` (default the largest value, or 1 for rates). Rows with no value get no bar. */
export function barRows(rows, { max } = {}) {
  const top = max ?? Math.max(0, ...rows.map((r) => r.value ?? 0));
  return rows.map((r) => ({ ...r, share: r.value == null || top <= 0 ? null : Math.min(1, r.value / top) }));
}

/** Vertical columns for a run of sessions: each has the height share of its value against a common scale. */
export function columnBars(values, { max } = {}) {
  const top = niceMax(max ?? Math.max(0, ...values));
  return { max: top, bars: values.map((v) => ({ value: v, share: v / top })) };
}

export const percentText = (rate) => (rate == null ? "" : `${Math.round(rate * 100)}%`);
export const sessionsText = (n) => `${n} ${n === 1 ? "session" : "sessions"}`;
