// Gathers the stored counters for the teacher's "Reading aloud" view and hands them to the pure aggregation. Every read is bounded:
// one capped query for the totals, one for the last 8 weeks, and word counters for at most ORG_PASSAGES passages.
import { buildReadAloudInsights, classComparison, meetsMinimum, weeklySeries, wordKey } from "./aggregate.js";
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
export async function readAloudInsights({ store, timingOf, passages, classes, filters, now = Date.now() }) {
  const weekList = lastWeeks(WEEKS_SHOWN, now);
  const [allSummaries, weeks] = await Promise.all([store.readAloudSummaries(), store.readAloudWeeks(weekList[0])]);
  const known = new Set(passages.map((p) => p.id));
  const summaries = allSummaries.filter((s) => known.has(s.passageId));

  let wordGroups = [];
  let textOf = () => "";
  if (filters.passageId) {
    wordGroups = await store.readAloudWords(filters.passageId);
    textOf = textLookup(await timingOf(filters.passageId));
  } else {
    const pick = [...new Set(summaries.filter(meetsMinimum).filter((s) => !filters.classId || s.classId === filters.classId).sort((a, b) => b.sessions - a.sessions).map((s) => s.passageId))].slice(0, ORG_PASSAGES);
    const perPassage = await Promise.all(pick.map(async (id) => ({ id, groups: await store.readAloudWords(id), timing: await timingOf(id) })));
    wordGroups = perPassage.flatMap(({ groups, timing }) => groups.map((g) => ({ ...g, textOf: textLookup(timing), keys: keysOf(timing) })));
  }
  const base = buildReadAloudInsights({ summaries, wordGroups, passages, filters, textOf });
  const inPassage = summaries.filter((s) => !filters.passageId || s.passageId === filters.passageId);
  return {
    ...base,
    classes: classComparison(inPassage, classes),
    weeks: weeklySeries(weeks, summaries, filters, weekList),
  };
}

/** The reader view of one class. Refuses (null) unless the class's "progress by reader" switch is on, so codes are never returned otherwise. */
export async function readerInsights({ store, timingOf, classId, code, passageId }) {
  const settings = effectiveClassSettings(await store.getClassSettings(), classId);
  if (!settings.readers) return null;
  const items = await store.readAloudReaders(classId);
  const timings = new Map(await Promise.all([...new Set(items.map((i) => i.passageId))].map(async (id) => [id, textLookup(await timingOf(id))])));
  const readers = listReaders(items);
  return {
    classId,
    readers,
    selected: code && readers.some((r) => r.code === code) ? readerDetail(items, { code, passageId }, (id) => timings.get(id) ?? (() => "")) : null,
  };
}

export { classSettingsView };
