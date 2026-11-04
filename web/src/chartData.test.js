import assert from "node:assert/strict";
import { test } from "node:test";
import { areaOf, barRows, columnBars, dayLabel, linePoints, niceMax, pathOf, percentText, sessionsText } from "./chartData.js";

test("niceMax gives round bounds and never zero", () => {
  assert.deepEqual([0, 0.5, 7, 14, 22, 101, 430].map(niceMax), [1, 1, 10, 15, 25, 200, 500]);
  assert.equal(niceMax(NaN), 1);
});

test("dayLabel reads an ISO date and ignores anything else", () => {
  assert.equal(dayLabel("2026-11-02"), "Nov 2");
  assert.equal(dayLabel("nope"), "");
});

const box = { width: 200, height: 100, left: 20, right: 10, top: 10, bottom: 20 };

test("line points are spread evenly, zero sits on the baseline and the biggest value on the top", () => {
  const { points, baseline, max } = linePoints([0, 5, 10], ["a", "b", "c"], box);
  assert.equal(max, 10);
  assert.deepEqual(points.map((p) => p.x), [20, 105, 190]);
  assert.equal(points[0].y, baseline);
  assert.equal(points[2].y, 10);
  assert.equal(points[1].label, "b");
});

test("a missing value breaks the line instead of drawing zero", () => {
  const { points, segments } = linePoints([2, null, 4, 6], ["a", "b", "c", "d"], box);
  assert.equal(points[1].y, null);
  assert.deepEqual(segments.map((s) => s.length), [1, 2]);
});

test("a fixed max is honoured (rates run to 100) and one value is centred", () => {
  const one = linePoints([50], ["x"], { ...box, max: 100 });
  assert.equal(one.max, 100);
  assert.equal(one.points[0].x, 105);
});

test("paths and areas", () => {
  const { segments, baseline } = linePoints([1, 2], ["a", "b"], box);
  assert.match(pathOf(segments[0]), /^M20\.0 \d+\.\d L190\.0 /);
  assert.match(areaOf(segments[0], baseline), /Z$/);
  assert.equal(areaOf([segments[0][0]], baseline), "");
});

test("bar rows scale against the largest value or a fixed max; no value means no bar", () => {
  assert.deepEqual(barRows([{ value: 5 }, { value: 10 }, { value: null }]).map((r) => r.share), [0.5, 1, null]);
  assert.deepEqual(barRows([{ value: 0.4 }], { max: 1 }).map((r) => r.share), [0.4]);
  assert.deepEqual(barRows([{ value: 0 }]).map((r) => r.share), [null]);
});

test("columns share one scale", () => {
  const { max, bars } = columnBars([1, 3, 0]);
  assert.equal(max, 3);
  assert.deepEqual(bars.map((b) => b.share), [1 / 3, 1, 0]);
});

test("texts", () => {
  assert.equal(percentText(0.456), "46%");
  assert.equal(percentText(null), "");
  assert.deepEqual([1, 2].map(sessionsText), ["1 session", "2 sessions"]);
});
