// Syllables for the pronunciation help. English patterns are fetched only when the help opens (dynamic import: its own small chunk);
// Spanish is a rule set bundled with the help. Nothing here touches the network at run time and nothing about the learner is stored.
import { splitSpanish } from "./syllablesEs.js";

const cache = new Map();

/** The word without punctuation around it (inner apostrophes and hyphens stay). */
export const displayWord = (text) =>
  String(text ?? "")
    .trim()
    .replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");

async function build(language) {
  if (language === "es") return splitSpanish;
  const [{ default: Hypher }, { default: patterns }, { createEnglishSplitter }] = await Promise.all([
    import("hypher"),
    import("hyphenation.en-us"),
    import("./syllablesEn.js"),
  ]);
  return createEnglishSplitter(Hypher, patterns);
}

/** The splitter for "en" or "es" (anything else is English), loaded once. */
export function loadSplitter(language) {
  const key = language === "es" ? "es" : "en";
  if (!cache.has(key)) {
    const pending = build(key).catch((error) => {
      cache.delete(key); // allow a retry
      throw error;
    });
    cache.set(key, pending);
  }
  return cache.get(key);
}

/** Syllables of a passage word, original letters kept. [] when there is no word. Rejects only if the patterns cannot be loaded. */
export async function syllablesFor(text, language) {
  const word = displayWord(text);
  if (!word) return [];
  const split = await loadSplitter(language);
  const pieces = split(word);
  return pieces.length ? pieces : [word];
}
