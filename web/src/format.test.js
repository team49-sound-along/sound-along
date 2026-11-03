import { test } from "node:test";
import assert from "node:assert/strict";
import { formatMs, formatShare, formatMos, DASH, formatDuration, formatCount, formatUsd, formatPercent, formatRtf, percentOf, formatDate, formatMinutes } from "./format.js";

test("duration formats mm:ss and guards bad input", () => {
  assert.equal(formatDuration(125000), "2:05");
  assert.equal(formatDuration(null), DASH);
  assert.equal(formatDuration(-5), DASH);
});
test("counts and minutes", () => {
  assert.equal(formatCount(12345), "12,345");
  assert.equal(formatCount(undefined), DASH);
  assert.equal(formatMinutes(3.46), "3.5 min");
});
test("usd keeps precision for tiny amounts", () => {
  assert.equal(formatUsd(0.0031), "$0.0031");
  assert.equal(formatUsd(320), "$320");
  assert.equal(formatUsd(12.5), "$12.50");
  assert.equal(formatUsd(NaN), DASH);
});
test("percent and rtf", () => {
  assert.equal(formatPercent(99.456), "99.5%");
  assert.equal(formatRtf(0.1234), "0.12×");
  assert.equal(formatRtf(null), DASH);
});
test("percentOf handles zero total", () => {
  assert.equal(percentOf(1, 4), 25);
  assert.equal(percentOf(1, 0), null);
  assert.equal(percentOf(undefined, 3), null);
});
test("date-only strings do not shift timezone", () => {
  assert.equal(formatDate("2026-03-04"), "Mar 4, 2026");
  assert.equal(formatDate(null), DASH);
  assert.equal(formatDate("nope"), DASH);
});

test("formatMs, formatShare and formatMos handle values and gaps", () => {
  assert.equal(formatMs(40.4), "40 ms");
  assert.equal(formatMs(1234), "1,234 ms");
  assert.equal(formatMs(undefined), DASH);
  assert.equal(formatShare(0.884), "88%");
  assert.equal(formatShare(null), DASH);
  assert.equal(formatMos(4.512), "4.5");
  assert.equal(formatMos(NaN), DASH);
});

import { formatRating } from "./format.js";
test("formatRating shows one decimal out of five", () => {
  assert.equal(formatRating(4.123), "4.1 / 5");
  assert.equal(formatRating(3), "3.0 / 5");
  assert.equal(formatRating(null), DASH);
  assert.equal(formatRating(NaN), DASH);
});
