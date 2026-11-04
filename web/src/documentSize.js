// How big a pasted text is, and what will happen to it. The server makes the real decision (services/api/src/splitDocument.js); this is the preview.
export const SINGLE_WORDS_MAX = 1000;
export const DOCUMENT_WORDS_MAX = 12000;

/** Spoken words, counted like the server: whitespace plus one extra per em or en dash. */
export function countWords(text) {
  const t = String(text ?? "").trim();
  if (!t) return 0;
  return t.split(/[\s\x1c-\x1f\x85]+/).length + (t.match(/[–—]/g) ?? []).length;
}

/** { words, long, tooLong }: `long` is a text over one run (it takes a few minutes; it is still ONE passage), `tooLong` is over the overall limit. */
export function describeSize(text) {
  const words = countWords(text);
  return { words, long: words > SINGLE_WORDS_MAX, tooLong: words > DOCUMENT_WORDS_MAX };
}
