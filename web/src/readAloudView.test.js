import assert from "node:assert/strict";
import { test } from "node:test";
import { NOT_ENOUGH, classRateRows, rateNote, readerColumns, readerPoints, tiles, weekPoints, wordRows, wordsMessage } from "./readAloudView.js";

test("weeks become labelled line points", () => {
  assert.deepEqual(weekPoints([{ week: "2026-11-02", sessions: 1 }, { week: "2026-11-09", sessions: 4 }]), [
    { label: "Nov 2", value: 1, text: "1 session" },
    { label: "Nov 9", value: 4, text: "4 sessions" },
  ]);
  assert.deepEqual(weekPoints(undefined), []);
});

test("a class below the minimum has no bar and says so instead of showing numbers", () => {
  const rows = classRateRows([{ id: "a", name: "A", enough: true, finishRate: 0.5, retryRate: 0.2 }, { id: "b", name: "B", enough: false, finishRate: null, retryRate: null }], "finishRate", "finished");
  assert.deepEqual(rows.map((r) => [r.label, r.value, r.text]), [["A", 0.5, "50% finished"], ["B", null, ""]]);
  assert.equal(rows[1].note, NOT_ENOUGH);
});

test("words show the count out of the sessions", () => {
  assert.deepEqual(wordRows([{ word: "because", missed: 14, sessions: 22, share: 14 / 22 }]), [{ key: "because", label: "because", value: 14 / 22, text: "14 of 22 sessions", note: "" }]);
});

test("tiles show a dash when there is nothing, never a made-up rate", () => {
  assert.deepEqual(tiles({ sessions: 0, finishRate: null, retryRate: null }), { sessions: "—", finish: "—", retry: "—" });
  assert.deepEqual(tiles({ sessions: 22, finishRate: 15 / 22, retryRate: 0.25 }), { sessions: "22", finish: "68%", retry: "25%" });
  assert.deepEqual(tiles(undefined), { sessions: "—", finish: "—", retry: "—" });
});

test("a reader's sessions become points and columns", () => {
  const sessions = [{ n: 1, at: "2026-11-01", pct: 60, skipped: 3, differs: 1 }, { n: 2, at: "2026-11-03", pct: 80, skipped: 1, differs: 0 }];
  assert.deepEqual(readerPoints(sessions).map((p) => [p.label, p.value, p.text]), [["#1", 60, "60% of the passage read, Nov 1"], ["#2", 80, "80% of the passage read, Nov 3"]]);
  assert.deepEqual(readerColumns(sessions), [{ label: "#1", a: 3, b: 1 }, { label: "#2", a: 1, b: 0 }]);
});

test("the notices say why a list is missing and never name a student", () => {
  assert.match(wordsMessage({ state: "small" }, 2, 3), /at least 3 sessions.*one student's reading can never be picked out.*2 sessions so far are not shown/);
  assert.match(wordsMessage({ state: "small" }, 1, 3), /1 session so far is not shown/);
  assert.match(wordsMessage({ state: "none" }, 0, 3), /No reading-aloud sessions yet/);
  assert.equal(wordsMessage({ state: "ok" }, 0, 3), "");
  assert.equal(rateNote(0, 3), "");
  assert.equal(rateNote(2, 3), "2 sessions from groups with fewer than 3 sessions are left out.");
});
