// Client-side mirror of the pronunciation rules in docs/API.md v2. The server is the authority: show its messages verbatim.
export const WORD_RE = /^[a-z'-]{1,40}$/;
export const RESPELLING_MAX = 60;
const PLAIN_RE = /^[A-Za-z][A-Za-z -]*$/;

export const normalizeWord = (w) => String(w ?? "").trim().toLowerCase();

/** Returns {word?, respelling?} problems (empty when fine). Phonemes in slashes are not inspected further. */
export function validatePronunciation({ word, respelling }) {
  const errors = {};
  if (!WORD_RE.test(normalizeWord(word))) errors.word = "Use 1 to 40 lowercase letters, apostrophes or hyphens.";
  const r = String(respelling ?? "").trim();
  if (!r) errors.respelling = "Enter how the word should sound.";
  else if (r.length > RESPELLING_MAX) errors.respelling = `Keep the respelling to ${RESPELLING_MAX} characters or fewer.`;
  else if (!(PLAIN_RE.test(r) || (r.length > 2 && r.startsWith("/") && r.endsWith("/")))) errors.respelling = 'Use plain letters, spaces and hyphens (like "gay-uh-teez"), or phonemes between slashes.';
  return { valid: Object.keys(errors).length === 0, errors };
}

/** Insert or replace by word, keeping the list sorted by word. Returns a new array. */
export function upsertPronunciation(list, entry) {
  return [...list.filter((p) => p.word !== entry.word), entry].sort((a, b) => a.word.localeCompare(b.word));
}
export const removePronunciation = (list, word) => list.filter((p) => p.word !== word);
