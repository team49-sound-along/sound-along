import { test } from "node:test";
import assert from "node:assert/strict";
import { comparisonRows, isSmallSample, meanRows, narratorLabel } from "./blind.js";

const summary = {
  raters: 4, ratings: 12,
  comparisons: [{ comparison: "ai vs human", n: 7, preferredAi: 3, preferredOther: 3, tie: 1 }, { comparison: "mystery", n: 1, preferredAi: 0, preferredOther: 1, tie: 0 }],
  meanRating: { ai: 4.123, human: null, polly_current: 3 },
};

test("plain labels", () => {
  assert.equal(narratorLabel("ai"), "AI voice");
  assert.equal(narratorLabel("human"), "Human narrator");
  assert.equal(narratorLabel("polly_current"), "ReadWorks current audio");
  assert.equal(narratorLabel("zzz"), "zzz");
});
test("comparison rows keep counts and label known comparisons", () => {
  const rows = comparisonRows(summary);
  assert.equal(rows[0].label, "AI voice vs human narrator");
  assert.deepEqual([rows[0].n, rows[0].preferredAi, rows[0].preferredOther, rows[0].tie], [7, 3, 3, 1]);
  assert.equal(rows[1].label, "mystery");
  assert.deepEqual(comparisonRows(null), []);
});
test("mean rows cover all three narrators and null gaps", () => {
  const rows = meanRows(summary);
  assert.deepEqual(rows.map((r) => r.key), ["ai", "human", "polly_current"]);
  assert.equal(rows[1].value, null);
  assert.equal(meanRows(undefined).every((r) => r.value === null), true);
});
test("small sample and rating formatting", () => {
  assert.equal(isSmallSample(summary), true);
  assert.equal(isSmallSample({ ratings: 200 }), false);
  assert.equal(isSmallSample(null), true);
});
