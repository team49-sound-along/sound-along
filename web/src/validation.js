// Validation for the Generate form; limits mirror docs/API.md.
export const TITLE_MAX = 120;
export const TEXT_MIN = 20;
export const TEXT_MAX = 12000;

export function validateGenerate({ title = "", text = "" } = {}) {
  const errors = {};
  const t = String(title).trim();
  const len = String(text).length;
  if (t.length < 1) errors.title = "Enter a title.";
  else if (t.length > TITLE_MAX) errors.title = `Title must be ${TITLE_MAX} characters or fewer.`;
  if (len < TEXT_MIN) errors.text = `Passage text needs at least ${TEXT_MIN} characters.`;
  else if (len > TEXT_MAX) errors.text = `Passage text must be ${TEXT_MAX.toLocaleString("en-US")} characters or fewer.`;
  return { valid: Object.keys(errors).length === 0, errors };
}

/** Friendly message for generate failures by HTTP status. */
export function generateErrorMessage(status, fallback) {
  if (status === 429) return "Too many requests right now. Wait a minute, then try again.";
  if (status === 503) return "Audio generation is turned off on this server. You can still read the sample passages in the Library.";
  return fallback || "Something went wrong starting generation. Please try again.";
}
