// Validation for the Generate form; limits mirror docs/API.md.
import { DOCUMENT_WORDS_MAX, countWords } from "./documentSize.js";

export const TITLE_MAX = 120;
export const TEXT_MIN = 20;
export const TEXT_MAX = 100000;

export function validateGenerate({ title = "", text = "" } = {}) {
  const errors = {};
  const t = String(title).trim();
  const len = String(text).length;
  if (t.length < 1) errors.title = "Enter a title.";
  else if (t.length > TITLE_MAX) errors.title = `Title must be ${TITLE_MAX} characters or fewer.`;
  if (len < TEXT_MIN) errors.text = `Passage text needs at least ${TEXT_MIN} characters.`;
  else if (len > TEXT_MAX) errors.text = `Passage text must be ${TEXT_MAX.toLocaleString("en-US")} characters or fewer.`;
  else if (countWords(text) > DOCUMENT_WORDS_MAX) errors.text = `This is more than ${DOCUMENT_WORDS_MAX.toLocaleString("en-US")} words, the most that can be made at once (about 40 pages). Add it in volumes.`;
  return { valid: Object.keys(errors).length === 0, errors };
}

/** Friendly message for generate failures by HTTP status. */
export function generateErrorMessage(status, fallback) {
  if (status === 429) return "Too many requests right now. Wait a minute, then try again.";
  if (status === 503) return "Creating new audio is turned off right now. You can still read the passages in the Library.";
  return fallback || "Something went wrong starting generation. Please try again.";
}
