// Phrase lines: split a paragraph's words into lines at clause boundaries, where a reader naturally pauses.
// When the timing file carries `phraseEnd` flags the browser only draws them (the content documents hold the decisions).
// Without flags it falls back to the punctuation rule below. Research note: line breaks at clause ends improved rated phrasing for ages 7 to 9. Comprehension is unproven.

const MIN_WORDS = 3; // a comma only breaks a line that already has this many words
const MAX_WORDS = 10; // a run with no punctuation never goes past this
const SOFT_END = /[,;:—–]["')”’]*$/;
const HARD_END = /[.!?]["')”’]*$/;

/** Group words into lines. Words are returned by reference and the input is never changed. */
export function phraseLines(words) {
  if (!Array.isArray(words)) return [];
  const fromData = words.some((w) => typeof w?.phraseEnd === "boolean");
  return words.reduce(
    (state, word, index) => {
      const current = [...state.current, word];
      const next = words[index + 1];
      const text = String(word?.text ?? "");
      const endsSentence = !next || next.sentence !== word.sentence || HARD_END.test(text);
      const endsPhrase = fromData ? word.phraseEnd === true : SOFT_END.test(text) && current.length >= MIN_WORDS;
      const full = !fromData && current.length >= MAX_WORDS;
      return endsSentence || endsPhrase || full
        ? { lines: [...state.lines, current], current: [] }
        : { lines: state.lines, current };
    },
    { lines: [], current: [] },
  ).lines;
}

/** Sentence number of the active word, or null when nothing is active. */
export const activeSentence = (words, index) => words?.[index]?.sentence ?? null;

// Index of the first word of the sentence that contains word k.
const startOf = (words, k) => {
  let start = k;
  while (start > 0 && words[start - 1].sentence === words[k].sentence) start -= 1;
  return start;
};

/**
 * Where "back one sentence" or "forward one sentence" should land.
 * Forward: the first word of the next sentence, or null when there is none.
 * Back: the start of the current sentence, or the previous one when already at the start.
 */
export function sentenceStart(words, index, direction) {
  if (!Array.isArray(words) || words.length === 0 || index >= words.length) return null;
  if (index < 0) return 0;
  if (direction > 0) {
    const next = words.findIndex((w, j) => j > index && w.sentence !== words[index].sentence);
    return next === -1 ? null : next;
  }
  const here = startOf(words, index);
  return index > here || here === 0 ? here : startOf(words, here - 1);
}
