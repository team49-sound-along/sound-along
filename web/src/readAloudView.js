// Pure shaping of the "Reading aloud" API answers for the charts and numbers behind "Show the numbers". No DOM, no Vue.
import { dayLabel, percentText } from "./chartData.js";
import { DASH, formatCount } from "./format.js";
import { progressLabel } from "./progressPath.js";
import { readerLabel } from "./readerCode.js";

export const NOT_ENOUGH = "Not enough reads yet";
const readsText = (n) => `${n} ${n === 1 ? "read" : "reads"}`;

/** Reads per week (the last 8) as line points. */
export const weekPoints = (weeks) => (weeks ?? []).map((w) => ({ label: dayLabel(w.week), value: w.sessions, text: readsText(w.sessions) }));

/** The five hardest words as bars: the length is the share of readers who missed it, the text says how many. */
export const hardestRows = (items, n = 5) =>
  (items ?? []).slice(0, n).map((w) => ({ key: w.word, label: w.word, value: w.share, text: `${w.missed} of ${w.sessions} readers`, note: "" }));

/** One plain bar per reader (how much of the passage they read last time) with one word. In the order given: letters, never results. */
export const readerRows = (progress) =>
  (progress ?? []).map((r) => {
    const last = r.pcts.at(-1) ?? 0;
    return { key: r.code, label: readerLabel(r.code), value: last / 100, text: `${last}% · ${progressLabel(r.pcts).label}`, note: "" };
  });

/** The share (0 to 100) that finished each week, for "Are they improving?". A week with no reads has no dot. */
export const trendPoints = (weeks) =>
  (weeks ?? []).map((w) => {
    const has = w.sessions > 0;
    const value = has ? Math.round((w.finished / w.sessions) * 100) : null;
    return { label: dayLabel(w.week), value, text: has ? `${value}% finished` : "no reads" };
  });

/** A trend is drawn only when at least two weeks have reads; one week is not a direction. */
export const hasTrend = (weeks) => (weeks ?? []).filter((w) => w.sessions > 0).length >= 2;

/** One bar per class for a rate ("finishRate" or "retryRate"). A class below the minimum has no bar and says so. */
export const classRateRows = (classes, field, phrase) =>
  (classes ?? []).map((c) => ({
    key: `${field}-${c.id}`,
    label: c.name,
    value: c.enough ? c[field] : null,
    text: c.enough ? `${percentText(c[field])} ${phrase}` : "",
    note: NOT_ENOUGH,
  }));

/** The words most often skipped or heard differently: the bar is the share of reads, the text is "14 of 22 reads". */
export const wordRows = (items) =>
  (items ?? []).map((w) => ({ key: w.word, label: w.word, value: w.share, text: `${w.missed} of ${w.sessions} reads`, note: "" }));

/** The plain list behind "Show the numbers": "—" when there is nothing to show (never an invented zero rate). */
export function numbersList(totals) {
  const t = totals ?? {};
  const has = (t.sessions ?? 0) > 0;
  return [
    { label: "Reads", value: has ? formatCount(t.sessions) : DASH, note: "Times a student read the passage aloud" },
    { label: "Finished", value: has ? percentText(t.finishRate) : DASH, note: "Reads that reached the end" },
    { label: "Went back to re-read", value: has ? percentText(t.retryRate) : DASH, note: "Reads where a student read a part again" },
  ];
}

/** Friendly note about reads that are left out because their group is too small to show. */
export const leftOutNote = (hidden, min) =>
  hidden > 0 ? `${readsText(hidden)} from groups with fewer than ${min} readers ${hidden === 1 ? "is" : "are"} left out.` : "";
