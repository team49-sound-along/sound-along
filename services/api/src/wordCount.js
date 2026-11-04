/** Spoken words in a text, counted like the pipeline tokenizer: whitespace (Python also treats \x1c-\x1f and \x85 as space) and a split after each em/en dash. Slightly over-counts, never under. */
export function countWords(text) {
  const trimmed = String(text ?? "").trim();
  if (!trimmed) return 0;
  return trimmed.split(/[\s\x1c-\x1f\x85]+/).length + (trimmed.match(/[–—]/g) ?? []).length;
}
