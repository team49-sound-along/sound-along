/**
 * ReviewItem[] from each passage's `review.suspects`, minus dismissed words and words that already have a
 * pronunciation fix (both compared case-insensitively on the expected word). Passages with nothing left are omitted.
 */
export function buildReviewItems({ sources, dismissed, fixed }) {
  const hidden = new Set([...dismissed, ...fixed].map((w) => String(w).toLowerCase()));
  return sources.flatMap(({ id, title, review }) => {
    const suspects = (Array.isArray(review?.suspects) ? review.suspects : [])
      .filter((s) => typeof s?.expected === "string" && !hidden.has(s.expected.toLowerCase()))
      .map((s) => ({ expected: s.expected, heard: String(s.heard ?? "") }));
    return suspects.length === 0 ? [] : [{ passageId: id, title, source: review.source ?? "asr-check", suspects }];
  });
}
