// "Per reader" view, only for a class whose teacher switched on "Show progress by reader (anonymous codes)". A reader is a random code from
// one device, not a person: a shared device is one reader. No ranking between readers, no grades, no comparison; codes are listed in
// alphabetical order and every sentence is about the reading, never about the child.
import { wordKey } from "./aggregate.js";

export const MIN_REPEAT = 2; // a word is "repeatedly missed" when it was missed in at least this many of the reader's sessions
const SHIFT = 5; // percentage points between the early and the recent sessions before the summary says anything changed

const mean = (list) => list.reduce((a, b) => a + b, 0) / list.length;

/** The readers of a class: code, how many sessions, how many passages. Alphabetical, never by result. */
export function listReaders(items) {
  const byCode = new Map();
  for (const item of items) {
    const before = byCode.get(item.code) ?? { code: item.code, sessions: 0, passages: 0 };
    byCode.set(item.code, { ...before, sessions: before.sessions + item.sessions.length, passages: before.passages + 1 });
  }
  return [...byCode.values()].sort((a, b) => a.code.localeCompare(b.code));
}

/** One sentence, matter-of-fact, from the share of the passage read across the sessions (oldest first). */
export function readerSummary(sessions) {
  if (sessions.length < 2) return "Not enough sessions yet to show a pattern.";
  const half = Math.floor(sessions.length / 2);
  const early = mean(sessions.slice(0, half).map((s) => s.pct));
  const recent = mean(sessions.slice(-half).map((s) => s.pct));
  if (recent >= early + SHIFT) return "Reading steadily more of the passage.";
  if (recent <= early - SHIFT) return "Reading a little less of the passage lately. A shorter passage or a read-through together may help.";
  return "Reading about the same amount of the passage each time.";
}

/**
 * One reader's charts. `items` are the class's reader items for this code (one per passage); `passageId` narrows to one passage (null = all).
 * Sessions are ordered by day; `textOf(passageId)(position)` is the server's own word lookup.
 */
export function readerDetail(items, { code, passageId = null }, textOf) {
  const mine = items.filter((i) => i.code === code && (!passageId || i.passageId === passageId));
  const sessions = mine
    .flatMap((i) => i.sessions.map((s) => ({ ...s, passageId: i.passageId })))
    .sort((a, b) => a.at.localeCompare(b.at))
    .map((s, n) => ({ n: n + 1, ...s }));
  const missed = new Map();
  for (const item of mine) {
    const lookup = textOf(item.passageId);
    for (const [position, c] of Object.entries(item.words)) {
      const text = lookup(Number(position));
      const key = wordKey(text);
      if (!key) continue;
      const before = missed.get(key) ?? { word: String(text).replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, ""), missed: 0 };
      missed.set(key, { ...before, missed: before.missed + (c.s ?? 0) + (c.d ?? 0) });
    }
  }
  const words = [...missed.values()].filter((w) => w.missed >= MIN_REPEAT).sort((a, b) => b.missed - a.missed || a.word.localeCompare(b.word)).slice(0, 10);
  return { code, sessions, words, summary: readerSummary(sessions) };
}
