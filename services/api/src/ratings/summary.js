const COMPARISONS = Object.freeze(["human", "polly_current"]);
const KINDS = Object.freeze(["ai", "human", "polly_current"]);

const mean = (values) => (values.length === 0 ? null : Number((values.reduce((s, v) => s + v, 0) / values.length).toFixed(2)));

/**
 * RatingSummary from stored ratings (docs/API.md v3). A listener is a distinct raterId; a rating without
 * a raterId counts as its own anonymous listener. meanRating averages every score a kind received, rounded to 2 places.
 */
export function summarizeRatings(ratings) {
  const raters = new Set();
  let anonymous = 0;
  for (const r of ratings) {
    if (r.raterId) raters.add(r.raterId);
    else anonymous += 1;
  }
  const scores = Object.fromEntries(KINDS.map((k) => [k, []]));
  for (const r of ratings) {
    scores[r.kindA]?.push(r.ratingA);
    scores[r.kindB]?.push(r.ratingB);
  }
  return {
    raters: raters.size + anonymous,
    ratings: ratings.length,
    comparisons: COMPARISONS.map((other) => {
      const name = `ai vs ${other}`;
      const rows = ratings.filter((r) => r.comparison === name);
      return {
        comparison: name,
        n: rows.length,
        preferredAi: rows.filter((r) => r.preferredKind === "ai").length,
        preferredOther: rows.filter((r) => r.preferredKind === other).length,
        tie: rows.filter((r) => r.preferredKind === "tie").length,
      };
    }),
    meanRating: Object.fromEntries(KINDS.map((k) => [k, mean(scores[k])])),
  };
}
