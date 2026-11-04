// The teacher's story for "Reading aloud", in plain words: one headline sentence, a finished / stopped split, and a few "what to do next"
// cards. Pure rules over the numbers the API already returns (the API applies the minimum-group rule). No DOM, no Vue.

export const HARD_MIN_MISSES = 2; // a word is "hard" when at least this many reads missed it ...
export const HARD_MIN_SHARE = 0.25; // ... and at least this share of the reads
const MAX_CARDS = 3;
const MAX_WORDS_IN_CARD = 3;
const quote = (text) => `“${text}”`;
const plural = (n, one, many) => (n === 1 ? one : many);

/** "Almost everyone" / "Most" / "About half" / "Fewer than half" for the share of reads that reached the end. */
export function finishWords(rate) {
  if (rate == null) return "";
  if (rate >= 0.9) return "Almost everyone";
  if (rate >= 0.6) return "Most";
  if (rate >= 0.4) return "About half";
  return "Fewer than half";
}

/** The words many readers missed, in the order the API ranked them. */
export const hardWords = (items) => (items ?? []).filter((w) => w.missed >= HARD_MIN_MISSES && w.share >= HARD_MIN_SHARE);

const wordsOk = (words) => words?.state === "ok";

/** One or two plain sentences that change with the data. `who` is the class name ("" for all classes). */
export function headline({ who = "", title, totals, words }) {
  const name = who || "your students";
  if (!totals || totals.sessions === 0) return `Not enough reads yet to say how ${quote(title || "this passage")} is going.`;
  const band = finishWords(totals.finishRate);
  const lead = band === "Almost everyone" ? `Almost all of ${name}` : `${band} of ${name}`;
  const first = `${lead} finished ${quote(title || "this passage")}.`;
  if (!wordsOk(words)) return first;
  const n = hardWords(words.items).length;
  const second = n === 0 ? "No word tripped up many readers." : `${n} ${plural(n, "word", "words")} tripped up many readers.`;
  return `${first} ${second}`;
}

/** Finished and stopped part-way (a read that did not reach the end). Percentages add to 100. Null when there are no reads. */
export function finishSplit(totals) {
  if (!totals || !totals.sessions) return null;
  const finished = totals.finished;
  const finishedPercent = Math.round((finished / totals.sessions) * 100);
  return { finished, stopped: totals.sessions - finished, total: totals.sessions, finishedPercent, stoppedPercent: 100 - finishedPercent };
}

/** The passage to open first: the one with the most reads that can be shown, else the first one listed (it explains what is missing). */
export const defaultPassage = (passages) => (passages ?? []).find((p) => p.sessions > 0)?.id ?? passages?.[0]?.id ?? "";

/** The paragraph where most of the stumbling happens, or null (needs two paragraphs and a clear hot spot). */
function hotParagraph(heat) {
  const tokens = heat?.tokens ?? [];
  const sums = new Map();
  for (const t of tokens) sums.set(t.paragraph, { missed: (sums.get(t.paragraph)?.missed ?? 0) + t.missed, hard: (sums.get(t.paragraph)?.hard ?? 0) + (t.missed >= HARD_MIN_MISSES ? 1 : 0) });
  if (sums.size < 2) return null;
  const total = [...sums.values()].reduce((a, s) => a + s.missed, 0);
  const [paragraph, best] = [...sums.entries()].sort((a, b) => b[1].missed - a[1].missed || a[0] - b[0])[0];
  return best.hard >= 2 && best.missed >= total * 0.4 ? paragraph : null;
}

/**
 * Up to three plain next steps. Hidden (an empty list) when the word list is not ready, so thin data never produces advice.
 * @returns {{ id: string, title: string, detail: string, words?: string[], paragraph?: number }[]}
 */
export function suggestions({ totals, words, heat }) {
  if (!totals || totals.sessions === 0 || !wordsOk(words)) return [];
  const cards = [];
  if (totals.finishRate !== null && totals.finishRate < 0.5) {
    cards.push({ id: "tooHard", title: "This passage may be too hard", detail: `${totals.sessions - totals.finished} of ${totals.sessions} readers stopped before the end. Try reading the first paragraph together, or choose a shorter passage.` });
  }
  const hard = hardWords(words.items).slice(0, MAX_WORDS_IN_CARD);
  if (hard.length) {
    cards.push({ id: "words", title: hard.length === 1 ? "Practice this word together" : `Practice these ${hard.length} words together`, detail: "Say each one aloud, then find it in the passage.", words: hard.map((w) => w.word) });
  }
  const paragraph = hotParagraph(heat);
  if (paragraph !== null) cards.push({ id: "paragraph", title: `Re-read paragraph ${paragraph + 1} as a class`, detail: "Most of the stumbling is in this paragraph.", paragraph });
  if (totals.retryRate !== null && totals.retryRate >= 0.5) cards.push({ id: "retry", title: "Many went back to re-read", detail: "Pause on a hard sentence and read it together once." });
  if (cards.length === 0 && totals.finishRate !== null && totals.finishRate >= 0.6) cards.push({ id: "fine", title: "Nothing needs fixing", detail: "No word stands out. Keep this passage as it is." });
  return cards.slice(0, MAX_CARDS);
}
