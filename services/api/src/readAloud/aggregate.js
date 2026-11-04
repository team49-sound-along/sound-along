// Pure aggregation of anonymous read-aloud counters for the teacher view. No store, no network, nothing is changed in place.
//
// Minimum-group rule: a class (or the "no class" bucket) is counted only when it has at least MIN_SESSIONS sessions for the passage, so a
// number or word list can never come from one child's session. Because "all classes" is built only from groups that pass on their own,
// subtracting one class from the total can never reveal a smaller class.
import { suggestSteps } from "./suggest.js";

export const MIN_SESSIONS = 3;
export const TOP_WORDS = 10;

const rate = (part, whole) => (whole > 0 ? part / whole : null);
const keyOf = (text) => String(text ?? "").toLowerCase().normalize("NFC").replace(/[^\p{L}\p{N}]/gu, "");
const sumOf = (groups, pick) => groups.reduce((total, g) => total + pick(g), 0);

export const meetsMinimum = (group) => group.sessions >= MIN_SESSIONS;

/** Totals and rates for groups that already passed the minimum. */
export function totalsOf(groups) {
  const sessions = sumOf(groups, (g) => g.sessions);
  const finished = sumOf(groups, (g) => g.finished);
  const retried = sumOf(groups, (g) => g.retried);
  return { sessions, finished, retried, finishRate: rate(finished, sessions), retryRate: rate(retried, sessions) };
}

/**
 * Words most often skipped or heard differently, merged by the word's letters ("Because" and "because" are one word). `groups` carry
 * `words`: { [position]: { s: skipped, d: differs } }. `textOf(position)` is the server's own lookup in the passage timing file.
 */
export function rankWords(groups, textOf, sessions, limit = TOP_WORDS) {
  const merged = new Map();
  for (const group of groups) {
    for (const [position, counts] of Object.entries(group.words ?? {})) {
      const text = textOf(Number(position));
      const key = keyOf(text);
      if (!key) continue;
      const before = merged.get(key) ?? { word: String(text).replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, ""), skipped: 0, differs: 0 };
      merged.set(key, { ...before, skipped: before.skipped + (counts.s ?? 0), differs: before.differs + (counts.d ?? 0) });
    }
  }
  return [...merged.values()]
    .map((w) => ({ ...w, missed: Math.min(w.skipped + w.differs, sessions), sessions })) // the same word twice in a text must not exceed the number of sessions
    .filter((w) => w.missed > 0)
    .sort((a, b) => b.missed - a.missed || b.skipped - a.skipped || a.word.localeCompare(b.word))
    .slice(0, limit)
    .map((w) => ({ ...w, share: w.missed / sessions }));
}

function passageRows(summaries, titles) {
  const byPassage = new Map();
  for (const s of summaries) byPassage.set(s.passageId, [...(byPassage.get(s.passageId) ?? []), s]);
  return [...byPassage.entries()]
    .map(([id, groups]) => {
      const passing = groups.filter(meetsMinimum);
      const totals = totalsOf(passing);
      return { id, title: titles.get(id) ?? "Passage", sessions: totals.sessions, finishRate: totals.finishRate, hidden: sumOf(groups, (g) => g.sessions) - totals.sessions };
    })
    .sort((a, b) => b.sessions - a.sessions || a.title.localeCompare(b.title));
}

/**
 * @param summaries  every counted group: { passageId, classId|null, sessions, finished, retried }
 * @param wordGroups groups of the chosen passage with `words` (empty when no passage is chosen)
 * @param passages   passage list ({ id, title }) used for titles
 * @param filters    { passageId|null, classId|null }
 * @param textOf     position -> word text for the chosen passage (from the passage's timing file)
 */
export function buildReadAloudInsights({ summaries, wordGroups = [], passages, filters, textOf = () => "" }) {
  const titles = new Map(passages.map((p) => [p.id, p.title]));
  const inFilter = (g) => (!filters.passageId || g.passageId === filters.passageId) && (!filters.classId || g.classId === filters.classId);
  const selected = summaries.filter(inFilter);
  const passing = selected.filter(meetsMinimum);
  const totals = totalsOf(passing);
  const hiddenSessions = sumOf(selected, (g) => g.sessions) - totals.sessions;

  let words = { state: "choose", items: [] };
  if (filters.passageId) {
    const pool = wordGroups.filter((g) => (!filters.classId || g.classId === filters.classId) && meetsMinimum(g));
    const n = sumOf(pool, (g) => g.sessions);
    if (selected.length === 0) words = { state: "none", items: [] };
    else if (pool.length === 0) words = { state: "small", items: [] };
    else words = { state: "ok", items: rankWords(pool, textOf, n) };
  }
  return {
    minSessions: MIN_SESSIONS,
    filters: { passageId: filters.passageId ?? null, classId: filters.classId ?? null },
    totals,
    hiddenSessions,
    passages: passageRows(summaries.filter((s) => !filters.classId || s.classId === filters.classId), titles),
    words,
    steps: words.state === "ok" ? suggestSteps({ totals, words: words.items }) : [],
  };
}
