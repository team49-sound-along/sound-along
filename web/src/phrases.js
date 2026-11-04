// Phrase lines: split a paragraph's words into lines at clause boundaries, where a reader naturally pauses.
// The lines are always worked out here, from the words: `phraseEnd` flags stored in older timing files came from an earlier rule that left
// one-word lines ("... from | China,"), so they are ignored and every passage, old or new, is drawn by the same rule. Research note: line breaks at clause ends improved rated phrasing for ages 7 to 9. Comprehension is unproven.

const MIN_WORDS = 3; // a comma only breaks a line that already has this many words
const MAX_WORDS = 10; // a run with no punctuation never goes past this
const SOFT_END = /[,;:—–]["')”’]*$/;
const HARD_END = /[.!?]["')”’]*$/;

// Words a long clause is best split BEFORE: they start a new phrase ("... imported | to Great Britain | from China").
const STARTS_PHRASE = new Set(["to", "in", "on", "at", "by", "for", "from", "of", "with", "into", "onto", "over", "under", "after", "before", "during", "through",
  "and", "but", "or", "so", "that", "which", "who", "when", "while", "because", "if", "as", "than", "until",
  "a", "al", "con", "de", "del", "en", "para", "por", "y", "o", "pero", "que", "cuando", "mientras", "porque", "si", "como"]);
const MIN_PART = 3; // a split never leaves a part shorter than this (no one-word orphan lines such as "China,")

const wordKey = (w) => String(w?.text ?? "").toLowerCase().replace(/[^\p{L}]/gu, "");

/** Cut points (counts of words) that split a clause of `n` words into balanced parts, each near the middle and preferably before a phrase-starting word. */
function balancedCuts(clause) {
  const n = clause.length;
  const parts = Math.ceil(n / MAX_WORDS);
  const cuts = [];
  let from = 0;
  for (let k = 1; k < parts; k += 1) {
    const ideal = Math.round((n * k) / parts);
    const lo = Math.max(from + MIN_PART, ideal - 2);
    const hi = Math.min(n - MIN_PART * (parts - k), ideal + 2);
    let best = -1;
    for (let c = lo; c <= hi; c += 1) {
      if (clause[c]?.join === true) continue; // "good—" + "and" is one visual word: never cut inside it
      const startsPhrase = STARTS_PHRASE.has(wordKey(clause[c]));
      const better = best === -1 || (startsPhrase && !STARTS_PHRASE.has(wordKey(clause[best]))) || (startsPhrase === STARTS_PHRASE.has(wordKey(clause[best])) && Math.abs(c - ideal) < Math.abs(best - ideal));
      if (better) best = c;
    }
    const cut = best === -1 ? Math.min(Math.max(ideal, from + 1), n - 1) : best;
    cuts.push(cut);
    from = cut;
  }
  return cuts;
}

/** A clause longer than MAX_WORDS becomes two or more balanced lines instead of "ten words, then one word". */
function splitLongClause(clause) {
  if (clause.length <= MAX_WORDS) return [clause];
  const cuts = [0, ...balancedCuts(clause), clause.length];
  return cuts.slice(1).map((end, i) => clause.slice(cuts[i], end));
}

/** Group words into lines. Words are returned by reference and the input is never changed. */
export function phraseLines(words) {
  if (!Array.isArray(words)) return [];
  const fromData = false; // stored flags are deliberately not used (see the note at the top)
  const clauses = words.reduce(
    (state, word, index) => {
      const current = [...state.current, word];
      const next = words[index + 1];
      const text = String(word?.text ?? "");
      const endsSentence = !next || next.sentence !== word.sentence || HARD_END.test(text);
      const endsPhrase = fromData ? word.phraseEnd === true : SOFT_END.test(text) && current.length >= MIN_WORDS;
      const gluedToNext = next?.join === true && !endsSentence; // "good—" + "and" are one visual word: never put a line break between them
      return endsSentence || (endsPhrase && !gluedToNext)
        ? { lines: [...state.lines, current], current: [] }
        : { lines: state.lines, current };
    },
    { lines: [], current: [] },
  ).lines;
  return fromData ? clauses : clauses.flatMap(splitLongClause);
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
