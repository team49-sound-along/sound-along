// View model for Insights.quality.blindRating (docs/API.md v3).

export const NARRATOR_LABELS = { ai: "AI voice", human: "Human narrator", polly_current: "ReadWorks current audio" };
export const COMPARISON_LABELS = { "ai vs human": "AI voice vs human narrator", "ai vs polly_current": "AI voice vs ReadWorks current audio" };
/** Below this many ratings in a comparison the numbers are anecdotes. Shown as a caveat only. */
export const SMALL_SAMPLE = 30;

export const narratorLabel = (k) => NARRATOR_LABELS[k] ?? k;
export const comparisonLabel = (k) => COMPARISON_LABELS[k] ?? k;

export function comparisonRows(summary) {
  return (summary?.comparisons ?? []).map((c) => ({
    key: c.comparison,
    label: comparisonLabel(c.comparison),
    n: c.n,
    preferredAi: c.preferredAi,
    preferredOther: c.preferredOther,
    tie: c.tie,
  }));
}

export function meanRows(summary) {
  const mean = summary?.meanRating ?? {};
  return Object.keys(NARRATOR_LABELS).map((k) => ({ key: k, label: NARRATOR_LABELS[k], value: Number.isFinite(mean[k]) ? mean[k] : null }));
}

export const isSmallSample = (summary) => !summary || !(summary.ratings >= SMALL_SAMPLE);
