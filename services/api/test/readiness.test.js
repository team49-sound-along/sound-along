import assert from "node:assert/strict";
import test from "node:test";
import { splitReady } from "../src/readiness.js";

const NOW = Date.parse("2026-11-04T12:00:00Z");
const at = (minutesAgo) => new Date(NOW - minutesAgo * 60_000).toISOString();
const id = (n) => `00000000-0000-4000-8000-00000000000${n}`;
const SERIES = (index) => ({ id: id(9), index, total: 2, title: "Doc", partIds: [id(1), id(2)] });
const p = (n, extra = {}) => ({ id: id(n), title: `P${n}`, createdAt: at(1), ...extra });
const idsOf = (list) => list.map((x) => x.id);

test("passages without any marker are ready, so samples and older data are never hidden", () => {
  const { ready, pending } = splitReady([p(1), p(2, { translationOf: id(1) })], NOW);
  assert.deepEqual([idsOf(ready), pending], [[id(1), id(2)], []]);
});

test("a passage whose translation is still being made is pending, and is ready once the marker is gone", () => {
  assert.deepEqual(idsOf(splitReady([p(1, { held: true })], NOW).pending), [id(1)]);
  assert.deepEqual(idsOf(splitReady([p(1)], NOW).ready), [id(1)]);
});

test("a long document is ready only when every part is there and none is held", () => {
  const partial = [p(1, { series: SERIES(1) })]; // part 2 does not exist yet
  assert.equal(splitReady(partial, NOW).ready.length, 0);
  const held = [p(1, { series: SERIES(1) }), p(2, { series: SERIES(2), held: true })];
  assert.equal(splitReady(held, NOW).ready.length, 0);
  const done = [p(1, { series: SERIES(1) }), p(2, { series: SERIES(2) })];
  assert.equal(splitReady(done, NOW).ready.length, 2);
});

test("a translation is hidden while its original is hidden, so the two languages appear together", () => {
  const list = [p(1, { series: SERIES(1) }), p(3, { translationOf: id(1), series: SERIES(1) })];
  assert.equal(splitReady(list, NOW).ready.length, 0);
  const all = [p(1, { series: SERIES(1) }), p(2, { series: SERIES(2) }), p(3, { translationOf: id(1), series: SERIES(1) })];
  assert.equal(splitReady(all, NOW).ready.length, 3);
});

test("a document that stopped changing is shown as it is, so a failed part never hides the rest forever", () => {
  const old = [p(1, { series: SERIES(1), createdAt: at(45) })];
  assert.equal(splitReady(old, NOW).ready.length, 1);
  assert.equal(splitReady([p(1, { held: true, createdAt: at(45) })], NOW).ready.length, 1);
});

test("the input is not changed", () => {
  const list = [p(1, { held: true })];
  const copy = structuredClone(list);
  splitReady(list, NOW);
  assert.deepEqual(list, copy);
});
