import { HttpError } from "./http.js";
import { languageMismatch } from "./languageGuess.js";
import { UUID } from "./recordings/rules.js";

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const EVENT_TYPES = new Set(["play", "word_tap", "complete"]);

export const LIMITS = { titleMax: 120, textMin: 20, textMax: 12000, wordsMax: 1400 }; // wordsMax: measured ~0.5 s of narration + timing per word, so 1,400 words stays well inside the 900 s Lambda limit

const bad = (message) => {
  throw new HttpError(400, message);
};
const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

export function parseAssignmentInput(body, { passageIds, classIds }) {
  if (!isObject(body)) bad("Send a JSON object.");
  const { passageId, classId, soundAlong, dueDate } = body;
  if (!passageIds.has(passageId)) bad("Choose a passage from the library.");
  if (!classIds.has(classId)) bad("Choose one of your classes.");
  if (typeof soundAlong !== "boolean") bad("Say whether Sound Along is on or off.");
  if (dueDate != null && !(typeof dueDate === "string" && DATE.test(dueDate) && !Number.isNaN(Date.parse(dueDate)))) {
    bad("Due date must look like 2026-11-20.");
  }
  return { passageId, classId, soundAlong, dueDate: dueDate ?? null };
}

export function parseToggle(body) {
  if (!isObject(body) || typeof body.soundAlong !== "boolean") bad("Say whether Sound Along is on or off.");
  return { soundAlong: body.soundAlong };
}

/** "en" | "es"; absent means "en". */
export function parseLanguage(value) {
  if (value == null) return "en";
  if (value !== "en" && value !== "es") bad('Language must be "en" or "es".');
  return value;
}

export function parseGenerateInput(body) {
  if (!isObject(body)) bad("Send a JSON object.");
  const title = typeof body.title === "string" ? body.title.trim() : "";
  const text = typeof body.text === "string" ? body.text.replace(/\r\n/g, "\n").trim() : "";
  if (title.length < 1 || title.length > LIMITS.titleMax) bad(`Title must be 1 to ${LIMITS.titleMax} characters.`);
  if (text.length < LIMITS.textMin) bad(`Add at least ${LIMITS.textMin} characters of text.`);
  if (text.length > LIMITS.textMax) bad(`Text can be at most ${LIMITS.textMax.toLocaleString("en-US")} characters.`);
  // Count like the pipeline tokenizer: whitespace (Python also treats \x1c-\x1f and \x85 as space) and a split after each em/en dash. Slightly over-counts, never under.
  const words = text.split(/[\s\x1c-\x1f\x85]+/).length + (text.match(/[\u2013\u2014]/g) ?? []).length;
  if (words > LIMITS.wordsMax) bad(`This passage is ${words.toLocaleString("en-US")} words, which is too long to read aloud in one go. Split it into parts of up to ${LIMITS.wordsMax.toLocaleString("en-US")} words.`);
  let recordingId = null;
  if (body.recordingId != null) {
    if (typeof body.recordingId !== "string" || !UUID.test(body.recordingId)) bad("That recording id is not valid. Upload the recording again.");
    recordingId = body.recordingId;
  }
  const language = parseLanguage(body.language);
  const mismatch = languageMismatch(text, language);
  if (mismatch) bad(mismatch);
  return { title, text, recordingId, language };
}

export function parseEvent(body, passageIds) {
  if (!isObject(body)) bad("Send a JSON object.");
  if (!EVENT_TYPES.has(body.type)) bad("Unknown event type.");
  if (!passageIds.has(body.passageId)) bad("Unknown passage.");
  return { type: body.type, passageId: body.passageId };
}

const escapeHtml = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const SENTENCE_END = /[.!?\u2026:;"'\u201D\u2019\u00BB)\]]$/;
const WRAPPED_LINE_MIN = 40; // lines of a hard-wrapped paste (PDF, Word, email) are long; headings and poem lines are short

/**
 * Text copied from a PDF, Word file or email has a line break every 60-90 characters, in the middle of sentences. Treating each break as a paragraph
 * cuts sentences in half (and with them the translation, the pauses of the voice and the highlighting). A single line break is a soft wrap when the
 * line before it is long and does not end a sentence; a blank line, a short line (heading, poem) or a line that ends with punctuation is a real paragraph break.
 * "exam-\nple" is rejoined without the hyphen.
 */
export function unwrapLines(text) {
  const out = [];
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    const previous = out.length ? out[out.length - 1] : null;
    if (previous !== null && previous !== "" && trimmed !== "" && previous.length >= WRAPPED_LINE_MIN && !SENTENCE_END.test(previous)) {
      const hyphenated = /[A-Za-z\u00C0-\u017F]-$/.test(previous);
      if (hyphenated && /^[a-z\u00E0-\u017F]/.test(trimmed)) out[out.length - 1] = previous.slice(0, -1) + trimmed; // a word split across two lines
      else out[out.length - 1] = previous + (hyphenated ? "" : " ") + trimmed;
    } else {
      out.push(trimmed);
    }
  }
  return out.join("\n");
}

/**
 * Plain-text and Markdown files mark emphasis with characters that must not be read aloud or shown: _italic_ (Project Gutenberg), *italic*, **bold**,
 * `code`, "# Heading", "> quote", "- item" and [link](url). Only whole-word markers are removed, so snake_case words and a lone * stay as they are.
 */
export function stripMarkup(text) {
  return text
    .replace(/\[(?:illustration|image|figure|footnote|note)\b[^\]\n]{0,200}\]/gi, "") // editorial tags
    .replace(/(?<=[\p{L}\p{N}.,;:!?"\u201D)])\[\d{1,3}\]/gu, "") // footnote markers (after a letter, digit or punctuation, accents included): "cual[1]" would be read aloud as "cual uno"
    .replace(/[ \t]*-{2,3}[ \t]*(?=\S)/g, (m, offset, whole) => (offset === 0 || whole[offset - 1] === "\n" ? "\u2014" : " \u2014 ")) // typed dashes (--Hola, word -- word)
    .replace(/\[([^\]\n]{1,200})\]\((?:https?:\/\/|mailto:)[^)\s]*\)/g, "$1")
    .replace(/(^|[^\w*])\*{1,3}(?=\S)([^*\n]*?\S)\*{1,3}(?![\w*])/g, "$1$2")
    .replace(/(^|[^\w_])_{1,2}(?=[^\s_])([^_\n]*?[^\s_])_{1,2}(?![\w_])/g, "$1$2")
    .replace(/`([^`\n]+)`/g, "$1")
    .replace(/^[ \t]*#([^#\n]{1,80})#[ \t]*$/gm, "$1") // "#TITLE#" heading markers on a line of their own
    .replace(/^[ \t]{0,3}(?:#{1,6}[ \t]+|>[ \t]?|[-*+][ \t]+)/gm, "");
}

/** Plain text -> the same <p> structure the parser expects from ReadWorks content. */
export function textToHtml(text) {
  return unwrapLines(stripMarkup(text))
    .split(/\n{1,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean)
    .map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`)
    .join("\n");
}
