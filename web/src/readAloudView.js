// Pure shaping of the "Reading aloud" API answers into what the charts and tiles show. No DOM, no Vue.
import { dayLabel, percentText, sessionsText } from "./chartData.js";
import { DASH, formatCount } from "./format.js";

export const NOT_ENOUGH = "Not enough sessions yet";

/** Sessions per week (the last 8) as line points. */
export const weekPoints = (weeks) => (weeks ?? []).map((w) => ({ label: dayLabel(w.week), value: w.sessions, text: sessionsText(w.sessions) }));

/** One bar per class for a rate ("finishRate" or "retryRate"). A class below the minimum has no bar and says so. */
export const classRateRows = (classes, field, phrase) =>
  (classes ?? []).map((c) => ({
    key: `${field}-${c.id}`,
    label: c.name,
    value: c.enough ? c[field] : null,
    text: c.enough ? `${percentText(c[field])} ${phrase}` : "",
    note: NOT_ENOUGH,
  }));

/** The words most often skipped or heard differently: the bar is the share of sessions, the text is "14 of 22 sessions". */
export const wordRows = (items) =>
  (items ?? []).map((w) => ({ key: w.word, label: w.word, value: w.share, text: `${w.missed} of ${w.sessions} sessions`, note: "" }));

/** Tiles: "—" when there is nothing to show (never an invented zero rate). */
export function tiles(totals) {
  const t = totals ?? {};
  const has = (t.sessions ?? 0) > 0;
  return {
    sessions: has ? formatCount(t.sessions) : DASH,
    finish: has ? percentText(t.finishRate) : DASH,
    retry: has ? percentText(t.retryRate) : DASH,
  };
}

/** One reader's share of the passage read, per session, as line points (0 to 100). */
export const readerPoints = (sessions) => (sessions ?? []).map((s) => ({ label: `#${s.n}`, value: s.pct, text: `${s.pct}% of the passage read, ${dayLabel(s.at)}` }));

/** Skipped and different words per session, as two-count columns. */
export const readerColumns = (sessions) => (sessions ?? []).map((s) => ({ label: `#${s.n}`, a: s.skipped, b: s.differs }));

/** What to say instead of a word list. */
export function wordsMessage(words, hiddenSessions, minSessions) {
  if (words.state === "none") return "No reading-aloud sessions yet for this choice.";
  if (words.state === "small") {
    const hidden = hiddenSessions > 0 ? ` ${sessionsText(hiddenSessions)} so far ${hiddenSessions === 1 ? "is" : "are"} not shown.` : "";
    return `Word lists appear once at least ${minSessions} sessions are counted (${minSessions} different readers when reader codes are on), so one student's reading can never be picked out.${hidden}`;
  }
  return "";
}

export const rateNote = (hiddenSessions, minSessions) =>
  hiddenSessions > 0 ? `${sessionsText(hiddenSessions)} from groups with fewer than ${minSessions} sessions ${hiddenSessions === 1 ? "is" : "are"} left out.` : "";
