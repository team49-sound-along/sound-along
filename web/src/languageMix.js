// A document that mixes two languages (a bilingual textbook with English notes and Spanish text, say) cannot be read by one voice. This finds the mix so the
// teacher can keep just one language, paragraph by paragraph. Paragraphs are separated by blank lines.
import { guessLanguage } from "./languageGuess.js";

const SHORT_HITS = 3; // a paragraph is short: three common words are enough to recognise its language
const MIN_MINORITY_WORDS = 30;
const MIN_MINORITY_SHARE = 0.12;

const wordsIn = (s) => (s.match(/[\p{L}\p{N}'’-]+/gu) ?? []).length;

/** { paragraphs: [{ text, lang, words }], words: { en, es }, mixed, minority } */
export function analyzeMix(text) {
  const paragraphs = String(text ?? "").split(/\n[ \t]*\n/).map((p) => p.trim()).filter(Boolean).map((p) => ({ text: p, lang: guessLanguage(p, SHORT_HITS), words: wordsIn(p) }));
  const words = { en: 0, es: 0 };
  for (const p of paragraphs) if (p.lang) words[p.lang] += p.words;
  const total = words.en + words.es;
  const minority = words.en <= words.es ? "en" : "es";
  const majority = minority === "en" ? "es" : "en";
  const mixed = total > 0 && words[minority] >= MIN_MINORITY_WORDS && words[minority] / total >= MIN_MINORITY_SHARE;
  return { paragraphs, words, mixed, minority, majority: mixed ? majority : null };
}

/** The text without the paragraphs written in the other language. Paragraphs whose language is unclear (headings, one-word lines) are kept. */
export function keepLanguage(text, lang) {
  return analyzeMix(text).paragraphs.filter((p) => p.lang === null || p.lang === lang).map((p) => p.text).join("\n\n");
}
