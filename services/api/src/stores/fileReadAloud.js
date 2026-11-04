import { dayOf, weekStart } from "../readAloud/weeks.js";

export const NO_CLASS = "-";
export const RETENTION_DAYS = 400;
export const READER_SESSIONS = 10; // the last sessions kept per reader and passage
export const READERS_PER_CLASS = 300;
const DAY_MS = 86_400_000;

const flagCounts = (existing, flags) =>
  flags.reduce((acc, { i, kind }) => {
    const before = acc[i] ?? { s: 0, d: 0 };
    return { ...acc, [i]: kind === "skipped" ? { ...before, s: before.s + 1 } : { ...before, d: before.d + 1 } };
  }, existing);
const fresh = (updatedAt, now) => now - Date.parse(updatedAt) < RETENTION_DAYS * DAY_MS;
const classOf = (key) => (key === NO_CLASS ? null : key);

/** One reader's session as kept: a day, a percentage and two counts. Nothing about which words (that is in the miss counters). */
export const readerSession = (result, now) => ({
  at: dayOf(now),
  pct: Math.round((result.wordsRead * 100) / result.wordsTotal),
  skipped: result.words.filter((w) => w.kind === "skipped").length,
  differs: result.words.filter((w) => w.kind === "differs").length,
  finished: result.finished,
});

/**
 * Anonymous read-aloud counters and class switches for the file store. Per passage and class only counters are kept (sessions, finished,
 * retried, and per word position how often it was skipped or heard differently), per calendar week the same three totals, and, only when a
 * result carries a reader code (class switch on), a short list of that code's last sessions. Nothing here names anyone. Anything untouched
 * for RETENTION_DAYS is dropped the next time its passage or class is written.
 */
export function createFileReadAloudMethods({ load, commit }) {
  return {
    async recordReadAloud(result, now = Date.now()) {
      const key = result.classId ?? NO_CLASS;
      await commit((s) => {
        const passage = s.readAloud?.[result.passageId] ?? {};
        const live = Object.fromEntries(Object.entries(passage).filter(([, g]) => fresh(g.updatedAt, now)));
        const before = live[key] ?? { sessions: 0, finished: 0, retried: 0, words: {} };
        const group = {
          sessions: before.sessions + 1,
          finished: before.finished + (result.finished ? 1 : 0),
          retried: before.retried + (result.retried > 0 ? 1 : 0),
          words: flagCounts(before.words, result.words),
          updatedAt: new Date(now).toISOString(),
        };
        const week = weekStart(now);
        const weekKey = `${result.passageId}#${key}`;
        const weeks = Object.fromEntries(Object.entries(s.readAloudWeeks ?? {}).filter(([w]) => fresh(w, now)));
        const w0 = weeks[week]?.[weekKey] ?? { sessions: 0, finished: 0, retried: 0 };
        const w1 = { sessions: w0.sessions + 1, finished: w0.finished + (result.finished ? 1 : 0), retried: w0.retried + (result.retried > 0 ? 1 : 0) };
        return {
          ...s,
          readAloud: { ...s.readAloud, [result.passageId]: { ...live, [key]: group } },
          readAloudWeeks: { ...weeks, [week]: { ...weeks[week], [weekKey]: w1 } },
          readAloudReaders: result.readerCode ? withReader(s.readAloudReaders, key, result, now) : s.readAloudReaders,
        };
      });
    },
    async readAloudSummaries() {
      const all = (await load()).readAloud ?? {};
      return Object.entries(all).flatMap(([passageId, groups]) =>
        Object.entries(groups).map(([key, g]) => ({ passageId, classId: classOf(key), sessions: g.sessions, finished: g.finished, retried: g.retried })),
      );
    },
    async readAloudWords(passageId) {
      const groups = (await load()).readAloud?.[passageId] ?? {};
      return Object.entries(groups).map(([key, g]) => ({ passageId, classId: classOf(key), sessions: g.sessions, words: g.words }));
    },
    async readAloudWeeks(fromWeek) {
      const all = (await load()).readAloudWeeks ?? {};
      return Object.entries(all)
        .filter(([week]) => week >= fromWeek)
        .flatMap(([week, groups]) =>
          Object.entries(groups).map(([k, g]) => {
            const [passageId, key] = k.split("#");
            return { week, passageId, classId: classOf(key), ...g };
          }),
        );
    },
    /** Reader items of one class (null = no class): { code, passageId, sessions: [...], words }. Bounded by READERS_PER_CLASS. */
    async readAloudReaders(classId) {
      const items = (await load()).readAloudReaders?.[classId ?? NO_CLASS] ?? {};
      return Object.entries(items).map(([k, v]) => {
        const [code, passageId] = k.split("#");
        return { code, passageId, sessions: v.sessions, words: v.words };
      });
    },
    async getClassSettings() {
      return { ...((await load()).classSettings ?? {}) };
    },
    async putClassSettings(key, patch) {
      await commit((s) => ({ ...s, classSettings: { ...s.classSettings, [key]: { ...s.classSettings?.[key], ...patch } } }));
    },
  };
}

function withReader(all, classKey, result, now) {
  const items = all?.[classKey] ?? {};
  const k = `${result.readerCode}#${result.passageId}`;
  const before = items[k] ?? { sessions: [], words: {}, updatedAt: "" };
  const next = {
    sessions: [...before.sessions, readerSession(result, now)].slice(-READER_SESSIONS),
    words: flagCounts(before.words, result.words),
    updatedAt: new Date(now).toISOString(),
  };
  const kept = Object.entries({ ...items, [k]: next })
    .filter(([, v]) => fresh(v.updatedAt, now))
    .sort((a, b) => b[1].updatedAt.localeCompare(a[1].updatedAt))
    .slice(0, READERS_PER_CLASS);
  return { ...all, [classKey]: Object.fromEntries(kept) };
}
