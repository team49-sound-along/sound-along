// What to show on each passage word while the learner reads aloud. Pure: the reader draws the returned marks.
// Marks: "read" (heard), "next" (the word to read now), "skipped", "differs" (heard as another word). Each has its own shape in
// readAloud.css, so no mark depends on colour alone.
import { cursorIndex } from "./readAloud.js";

/** @param state follower state  @param callout the event that stopped listening ({type, index, indexes}) or null */
export function marksFor(state, callout) {
  const marks = Object.fromEntries(Object.keys(state.read).map((index) => [index, "read"]));
  Object.entries(state.missed ?? {}).forEach(([index, m]) => (marks[index] = m.kind === "skipped" ? "skipped" : "differs")); // "keep going" mode: missed words stay marked
  if (callout?.type === "skipped") (callout.indexes ?? [callout.index]).forEach((i) => (marks[i] = "skipped"));
  else if (callout?.type === "differs") marks[callout.index] = "differs";
  else if (!state.done) {
    const next = cursorIndex(state);
    if (next !== null) marks[next] = "next";
  }
  return marks;
}

/** A cheap fingerprint of what the marks would be: the panel re-emits marks only when it changes, so a long passage is not redrawn for every interim result. */
export function marksSignature(state, callout) {
  const stop = callout ? `${callout.type}:${callout.index}:${(callout.indexes ?? []).join(",")}` : "";
  return `${Object.keys(state.read).length}|${Object.keys(state.missed ?? {}).join(",")}|${state.done ? "d" : cursorIndex(state)}|${stop}`;
}

/** First word index and the words of the sentence holding `index`, so the learner can restart the sentence. */
export function sentenceAround(words, index) {
  const sentence = words[index]?.sentence;
  const members = Array.isArray(words) && sentence !== undefined ? words.filter((w) => w?.sentence === sentence) : [];
  return members.length ? { start: members[0].i ?? words.indexOf(members[0]), words: members } : { start: Math.max(0, index), words: [words[index]].filter(Boolean) };
}

/** Plain sentences for the status line, kept here so they can be tested. */
export function calloutText(callout, words) {
  if (!callout) return "";
  const said = (i) => words[i]?.text ?? "";
  if (callout.type === "skipped") {
    if (callout.indexes.length > 6) {
      const lines = new Set(callout.indexes.map((i) => words[i]?.sentence)).size;
      const where = lines > 1 ? `${callout.indexes.length} words (${lines} sentences)` : `${callout.indexes.length} words`;
      return `You skipped ${where}, from “${said(callout.indexes[0])}” to “${said(callout.indexes.at(-1))}”. Read from the start of that part again.`;
    }
    const list = callout.indexes.map((i) => `“${said(i)}”`);
    const joined = list.length > 1 ? `${list.slice(0, -1).join(", ")} and ${list.at(-1)}` : list[0];
    return `You skipped ${joined}. Read from here again.`;
  }
  return `We heard “${callout.heard}” where the text says “${said(callout.index)}”. Read from here again.`;
}

/** One short, calm line for the reminder shown while the learner keeps reading ("keep going" mode). */
export function nudgeText(miss, words) {
  if (!miss) return "";
  const said = (i) => words[i]?.text ?? "";
  if (miss.kind === "differs") return `We heard “${miss.heard}” where the text says “${said(miss.index)}”.`;
  const n = miss.indexes.length;
  if (n === 1) return `You missed “${said(miss.index)}”.`;
  if (n <= 3) return `You missed ${miss.indexes.map((i) => `“${said(i)}”`).join(", ")}.`;
  return `You missed ${n} words, from “${said(miss.indexes[0])}” to “${said(miss.indexes.at(-1))}”.`;
}
