import assert from "node:assert/strict";
import { test } from "node:test";
import { NOT_ENOUGH, classRateRows, hardestRows, hasTrend, leftOutNote, numbersList, readerRows, trendPoints, weekPoints, wordRows } from "./readAloudView.js";

test("weeks become labelled line points, in reads", () => {
  assert.deepEqual(weekPoints([{ week: "2026-11-02", sessions: 1 }, { week: "2026-11-09", sessions: 4 }]), [
    { label: "Nov 2", value: 1, text: "1 read" },
    { label: "Nov 9", value: 4, text: "4 reads" },
  ]);
  assert.deepEqual(weekPoints(undefined), []);
});

test("the trend is the share that finished each week; a week with no reads has no dot", () => {
  const weeks = [{ week: "2026-11-02", sessions: 0, finished: 0 }, { week: "2026-11-09", sessions: 4, finished: 1 }, { week: "2026-11-16", sessions: 10, finished: 8 }];
  assert.deepEqual(trendPoints(weeks), [
    { label: "Nov 2", value: null, text: "no reads" },
    { label: "Nov 9", value: 25, text: "25% finished" },
    { label: "Nov 16", value: 80, text: "80% finished" },
  ]);
  assert.deepEqual(trendPoints(undefined), []);
});

test("the hardest words chart shows at most five bars, with the count beside each", () => {
  const items = Array.from({ length: 7 }, (_, n) => ({ word: `w${n}`, missed: 10 - n, sessions: 14, share: (10 - n) / 14 }));
  const rows = hardestRows(items);
  assert.equal(rows.length, 5);
  assert.deepEqual(rows[0], { key: "w0", label: "w0", value: 10 / 14, text: "10 of 14 readers", note: "" });
  assert.deepEqual(hardestRows(undefined), []);
});

test("each reader is one bar: how much of the passage they read last time, and one word", () => {
  const rows = readerRows([{ code: "KQ7MNW2X", pcts: [30, 45, 62, 80] }, { code: "PQ5WTN4K", pcts: [20, 25] }, { code: "MA8GFJ2S", pcts: [90] }]);
  assert.deepEqual(rows.map((r) => [r.value, r.text]), [[0.8, "80% · Improving"], [0.25, "25% · Support"], [0.9, "90% · New"]]);
  assert.match(rows[0].label, /KQ7M/);
  assert.deepEqual(readerRows(undefined), []);
});

test("a trend needs at least two weeks with reads", () => {
  assert.equal(hasTrend([{ sessions: 4, finished: 1 }, { sessions: 0, finished: 0 }]), false);
  assert.equal(hasTrend([{ sessions: 4, finished: 1 }, { sessions: 2, finished: 1 }]), true);
  assert.equal(hasTrend(undefined), false);
});

test("a class below the minimum has no bar and says so instead of showing numbers", () => {
  const rows = classRateRows([{ id: "a", name: "A", enough: true, finishRate: 0.5, retryRate: 0.2 }, { id: "b", name: "B", enough: false, finishRate: null, retryRate: null }], "finishRate", "finished");
  assert.deepEqual(rows.map((r) => [r.label, r.value, r.text]), [["A", 0.5, "50% finished"], ["B", null, ""]]);
  assert.equal(rows[1].note, NOT_ENOUGH);
});

test("words show the count out of the reads", () => {
  assert.deepEqual(wordRows([{ word: "because", missed: 14, sessions: 22, share: 14 / 22 }]), [{ key: "because", label: "because", value: 14 / 22, text: "14 of 22 reads", note: "" }]);
});

test("the numbers list shows a dash when there is nothing, never a made-up rate", () => {
  assert.deepEqual(numbersList({ sessions: 0, finishRate: null, retryRate: null }).map((r) => r.value), ["—", "—", "—"]);
  assert.deepEqual(numbersList({ sessions: 22, finishRate: 15 / 22, retryRate: 0.25 }).map((r) => [r.label, r.value]), [["Reads", "22"], ["Finished", "68%"], ["Went back to re-read", "25%"]]);
  assert.equal(numbersList(undefined)[0].value, "—");
});

test("the left-out note says why, in plain words, and never names a student", () => {
  assert.equal(leftOutNote(0, 3), "");
  assert.equal(leftOutNote(2, 3), "2 reads from groups with fewer than 3 readers are left out.");
  assert.equal(leftOutNote(1, 3), "1 read from groups with fewer than 3 readers is left out.");
});
