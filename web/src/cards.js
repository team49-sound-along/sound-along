// Word and place cards. The server route is described in docs/CARDS.md; until it exists the reader falls back
// to the vocabulary inside the passage's timing file, so these helpers accept either source.

/** Lower-case a word and strip punctuation from its edges. Inner apostrophes stay (there's). */
export const wordKey = (text) =>
  String(text ?? "")
    .toLowerCase()
    .replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");

/** Turn a timing-file vocabulary entry into the card shape. Missing parts become null or an empty list. */
export function cardFromVocab(entry) {
  if (!entry || !entry.word) return null;
  return {
    word: entry.word,
    syllables: null,
    ipa: null,
    partOfSpeech: entry.partOfSpeech ?? null,
    definition: entry.definition ?? "",
    example: entry.examples?.[0] ?? entry.example ?? null,
    spanish: Array.isArray(entry.spanish) ? entry.spanish : [],
  };
}

/** Server card first, then the passage vocabulary, otherwise null. */
export function findWordCard(cards, vocab, wordText) {
  const key = wordKey(wordText);
  if (!key) return null;
  const own = cards?.words && Object.hasOwn(cards.words, key) ? cards.words[key] : null;
  if (own) return own;
  const entry = Object.values(vocab ?? {}).find((v) => wordKey(v?.word) === key);
  return cardFromVocab(entry);
}

/** The place whose text covers the word at `index`, or null. Matches are case-insensitive and ignore punctuation. */
export function placeAt(words, index, places) {
  if (!Array.isArray(words) || !places || !Number.isInteger(index) || index < 0 || index >= words.length) return null;
  const entries = Object.entries(places).map(([name, place]) => ({ place, tokens: name.split(/\s+/).map(wordKey).filter(Boolean) }));
  const hit = entries.find(({ tokens }) => {
    const first = Math.max(0, index - tokens.length + 1);
    return tokens.length > 0 && Array.from({ length: index - first + 1 }, (_, n) => first + n).some(
      (start) => tokens.every((token, offset) => wordKey(words[start + offset]?.text) === token) && start + tokens.length > index,
    );
  });
  return hit ? hit.place : null;
}
