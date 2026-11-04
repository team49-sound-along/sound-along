// A long document becomes a series of parts, each short enough for one run of the generator (see docs/DEPLOY.md, "Long documents").
// Parts break at chapter headings and paragraph ends, never in the middle of a sentence unless a single paragraph is longer than a part.
import { countWords } from "./wordCount.js";

export const PART_TARGET_WORDS = 800;
export const PART_MAX_WORDS = 1000;
const PART_MIN_WORDS = 300; // do not close a part before it has this much, unless the next paragraph would not fit
const HEADING_BREAK_MIN_WORDS = 350; // a chapter heading starts a new part once the current one has this much
const LAST_PART_MIN_WORDS = 200; // a shorter last part is joined to the one before it when it fits

const HEADING_WORD = /^(chapter|cap[ií]tulo|part|parte|section|secci[oó]n|book|libro|act|acto|prologue|pr[oó]logo|epilogue|ep[ií]logo)\b/i;
const ABBREVIATIONS = new Set(["mr.", "mrs.", "ms.", "dr.", "st.", "jr.", "sr.", "prof.", "vs.", "sra.", "srta.", "dra.", "ud.", "uds.", "etc.", "no.", "u.s.", "ee.", "uu.", "a.m.", "p.m."]);
const TERMINAL = /[.!?…]["'”’»)]*$/;

/** A short line that is a title rather than a sentence: "CHAPTER II", "Capítulo 3", "IV", "THE RABBIT HOLE". */
export function isHeading(paragraph) {
  const p = paragraph.trim();
  const words = countWords(p);
  if (!p || words > 10 || /[.!?…,;:"”»)]$/.test(p)) return false;
  return HEADING_WORD.test(p) || /^[IVXLC]{1,7}$/.test(p) || /^\d{1,3}$/.test(p) || (p === p.toUpperCase() && /[A-ZÁÉÍÓÚÑ]/.test(p));
}

/** Sentences of a paragraph (for a paragraph that is longer than a whole part). Abbreviations and initials do not end a sentence. */
export function splitSentences(paragraph) {
  const tokens = paragraph.trim().split(/\s+/);
  const sentences = [];
  let current = [];
  tokens.forEach((token, i) => {
    current.push(token);
    const next = tokens[i + 1];
    const ends = TERMINAL.test(token) && !ABBREVIATIONS.has(token.toLowerCase().replace(/["'”’»)]+$/, "")) && !/^[A-Z]\.$/.test(token);
    if (ends && next && /^["'“‘«¿¡(]?[A-ZÁÉÍÓÚÑ\d]/.test(next)) {
      sentences.push(current.join(" "));
      current = [];
    }
  });
  if (current.length) sentences.push(current.join(" "));
  return sentences;
}

/** Cut a single run of text at word boundaries into pieces of at most `max` words (a sentence with no end in sight). */
function cutWords(text, max) {
  const words = text.split(/\s+/);
  const out = [];
  for (let i = 0; i < words.length; i += max) out.push(words.slice(i, i + max).join(" "));
  return out;
}

/** Paragraphs (strings) in order, with any paragraph longer than a part split into sentence groups of about PART_TARGET_WORDS. */
function units(paragraphs) {
  return paragraphs.flatMap((p) => {
    if (countWords(p) <= PART_MAX_WORDS) return [p];
    const groups = [];
    let current = [];
    let count = 0;
    for (const sentence of splitSentences(p).flatMap((s) => (countWords(s) > PART_MAX_WORDS ? cutWords(s, PART_TARGET_WORDS) : [s]))) {
      const w = countWords(sentence);
      if (current.length && count + w > PART_TARGET_WORDS) {
        groups.push(current.join(" "));
        current = [];
        count = 0;
      }
      current.push(sentence);
      count += w;
    }
    if (current.length) groups.push(current.join(" "));
    return groups;
  });
}

/** Splits cleaned text (paragraphs separated by line breaks) into parts of about PART_TARGET_WORDS words, at most PART_MAX_WORDS. Returns an array of strings. */
export function splitIntoParts(text) {
  const paragraphs = String(text ?? "").split(/\n+/).map((p) => p.trim()).filter(Boolean);
  const parts = [];
  let current = [];
  let count = 0;
  const close = () => {
    if (current.length) parts.push({ paragraphs: current, words: count });
    current = [];
    count = 0;
  };
  for (const unit of units(paragraphs)) {
    const w = countWords(unit);
    const fitsTarget = count + w <= PART_TARGET_WORDS;
    if (current.length && ((!fitsTarget && count >= PART_MIN_WORDS) || count + w > PART_MAX_WORDS || (isHeading(unit) && count >= HEADING_BREAK_MIN_WORDS))) close();
    current.push(unit);
    count += w;
  }
  close();
  const last = parts[parts.length - 1];
  const before = parts[parts.length - 2];
  if (last && before && last.words < LAST_PART_MIN_WORDS && before.words + last.words <= PART_MAX_WORDS) {
    before.paragraphs.push(...last.paragraphs);
    before.words += last.words;
    parts.pop();
  }
  return parts.map((p) => p.paragraphs.join("\n"));
}
