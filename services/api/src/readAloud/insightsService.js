// Gathers the stored counters for the teacher's "Reading aloud" view and hands them to the pure aggregation. Every read is bounded:
// one capped query for the totals, one for the last 8 weeks, and word counters for at most ORG_PASSAGES passages.
import { MIN_SESSIONS, buildReadAloudInsights, classComparison, meetsMinimum, weeklySeries, wordKey } from "./aggregate.js";
import { classSettingsView, effectiveClassSettings } from "./classSettings.js";
import { listReaders, readerDetail } from "./readers.js";
import { lastWeeks } from "./weeks.js";

export const WEEKS_SHOWN = 8;
export const ORG_PASSAGES = 20;

const textLookup = (timing) => {
  const byIndex = new Map((timing?.words ?? []).map((w) => [w.i, String(w.text ?? "")]));
  return (position) => byIndex.get(position) ?? "";
};
const keysOf = (timing) => new Set((timing?.words ?? []).map((w) => wordKey(w.text)).filter(Boolean));

/** @param ctx { store, timingOf(id), passages: [{id,title}], classes, filters: {passageId, classId}, now } */
/** Distinct reader codes per `${passage}#${class}` for the classes that use codes. Classes without codes are absent (their groups count sessions). */
async function distinctReaders(store, classes, readersEnabled) {
  if (!readersEnabled) return { counts: new Map(), coded: new Set() };
  const settings = await store.getClassSettings();
  const coded = new Set([null, ...classes.map((c) => c.id)].filter((id) => effectiveClassSettings(settings, id).readers));
  const counts = new Map();
  await Promise.all([...coded].map(async (classId) => {
    const sets = new Map();
    for (const item of await store.readAloudReaders(classId)) sets.set(item.passageId, new Set([...(sets.get(item.passageId) ?? []), item.code]));
    for (const [passageId, codes] of sets) counts.set(`${passageId}#${classId ?? "-"}`, codes.size);
  }));
  return { counts, coded };
}
const withDistinct = ({ counts, coded }) => (g) => ({ ...g, distinct: coded.has(g.classId ?? null) ? counts.get(`${g.passageId}#${g.classId ?? "-"}`) ?? 0 : null });

export async function readAloudInsights({ store, timingOf, passages, classes, filters, now = Date.now(), readersEnabled = false }) {
  const weekList = lastWeeks(WEEKS_SHOWN, now);
  const [allSummaries, weeks] = await Promise.all([store.readAloudSummaries(), store.readAloudWeeks(weekList[0])]);
  const known = new Set(passages.map((p) => p.id));
  const sources = await distinctReaders(store, classes, readersEnabled);
  const summaries = allSummaries.filter((s) => known.has(s.passageId)).map(withDistinct(sources));

  let wordGroups = [];
  let textOf = () => "";
  if (filters.passageId) {
    wordGroups = (await store.readAloudWords(filters.passageId)).map(withDistinct(sources));
    textOf = textLookup(await timingOf(filters.passageId));
  } else {
    const pick = [...new Set(summaries.filter(meetsMinimum).filter((s) => !filters.classId || s.classId === filters.classId).sort((a, b) => b.sessions - a.sessions).map((s) => s.passageId))].slice(0, ORG_PASSAGES);
    const perPassage = await Promise.all(pick.map(async (id) => ({ id, groups: await store.readAloudWords(id), timing: await timingOf(id) })));
    wordGroups = perPassage.flatMap(({ groups, timing }) => groups.map(withDistinct(sources)).map((g) => ({ ...g, textOf: textLookup(timing), keys: keysOf(timing) })));
  }
  const base = buildReadAloudInsights({ summaries, wordGroups, passages, filters, textOf });
  const inPassage = summaries.filter((s) => !filters.passageId || s.passageId === filters.passageId);
  return {
    ...base,
    classes: classComparison(inPassage, classes),
    weeks: weeklySeries(weeks, summaries, filters, weekList),
  };
}

export const READERS_SHOWN = 100;

/**
 * The reader view of one class. Defence in depth, since the API has no sign-in in this build: it returns an EMPTY view unless the class's
 * "progress by reader" switch is on (and sharing with it), and an empty view until the class has at least MIN_SESSIONS distinct reader codes, so a
 * lone code is never listed. The list is capped, and a code that is not in the class returns nothing.
 */
export async function readerInsights({ store, timingOf, classId, code, passageId }) {
  const empty = { classId, enabled: false, enough: false, readers: [], selected: null };
  const settings = effectiveClassSettings(await store.getClassSettings(), classId);
  if (!settings.readers) return empty;
  const items = await store.readAloudReaders(classId);
  if (new Set(items.map((i) => i.code)).size < MIN_SESSIONS) return { ...empty, enabled: true }; // fewer than 3 readers: a single reader would stand out
  const timings = new Map(await Promise.all([...new Set(items.map((i) => i.passageId))].map(async (id) => [id, textLookup(await timingOf(id))])));
  const readers = listReaders(items);
  return {
    classId,
    enabled: true,
    enough: true,
    readers: readers.slice(0, READERS_SHOWN),
    selected: code && readers.slice(0, READERS_SHOWN).some((r) => r.code === code) ? readerDetail(items, { code, passageId }, (id) => timings.get(id) ?? (() => "")) : null,
  };
}

export { classSettingsView };
