// What to show on each passage word while the learner reads aloud. Pure: the reader draws the returned marks.
// Marks: "read" (heard), "next" (the word to read now), "skipped", "differs" (heard as another word). Each has its own shape in
// readAloud.css, so no mark depends on colour alone.
import { cursorIndex } from "./readAloud.js";

/** @param state follower state  @param callout the event that stopped listening ({type, index, indexes}) or null */
export function marksFor(state, callout) {
  const marks = Object.fromEntries(Object.keys(state.read).map((index) => [index, "read"]));
  if (callout?.type === "skipped") (callout.indexes ?? [callout.index]).forEach((i) => (marks[i] = "skipped"));
  else if (callout?.type === "differs") marks[callout.index] = "differs";
  else if (!state.done) {
    const next = cursorIndex(state);
    if (next !== null) marks[next] = "next";
  }
  return marks;
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
    const list = callout.indexes.map((i) => `“${said(i)}”`);
    const joined = list.length > 1 ? `${list.slice(0, -1).join(", ")} and ${list.at(-1)}` : list[0];
    return `You skipped ${joined}. Read from here again.`;
  }
  return `We heard “${callout.heard}” where the text says “${said(callout.index)}”. Read from here again.`;
}
