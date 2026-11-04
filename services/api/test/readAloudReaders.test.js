import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { classComparison, weeklySeries } from "../src/readAloud/aggregate.js";
import { listReaders, readerDetail, readerSummary } from "../src/readAloud/readers.js";
import { lastWeeks, weekStart } from "../src/readAloud/weeks.js";

const s = (at, pct, skipped = 0, differs = 0) => ({ at, pct, skipped, differs, finished: pct === 100 });
const TEXT = ["the", "island", "because"];
const textOf = () => (i) => TEXT[i];

describe("weeks", () => {
  test("a week is named by its Monday and the list ends with this week", () => {
    assert.equal(weekStart(Date.parse("2026-11-04T10:00:00Z")), "2026-11-02");
    assert.equal(weekStart(Date.parse("2026-11-08T23:59:00Z")), "2026-11-02");
    assert.equal(weekStart(Date.parse("2026-11-09T00:00:00Z")), "2026-11-09");
    const list = lastWeeks(8, Date.parse("2026-11-04T10:00:00Z"));
    assert.equal(list.length, 8);
    assert.deepEqual([list[0], list[7]], ["2026-09-14", "2026-11-02"]);
  });
});

describe("class comparison and weekly series", () => {
  const classes = [{ id: "a", name: "A" }, { id: "b", name: "B" }];
  const sums = [{ passageId: "p", classId: "a", sessions: 10, finished: 5, retried: 2 }, { passageId: "p", classId: "b", sessions: 2, finished: 2, retried: 0 }];
  test("a class below the minimum has no numbers", () => {
    const [a, b] = classComparison(sums, classes);
    assert.deepEqual([a.enough, a.finishRate, a.retryRate], [true, 0.5, 0.2]);
    assert.deepEqual([b.enough, b.finishRate, b.retryRate, b.sessions], [false, null, null, null]);
    assert.equal(b.hidden, 2);
  });
  test("the weekly series is zero-filled, limited to the weeks asked for and to groups that pass the minimum", () => {
    const weeks = [
      { week: "2026-11-02", passageId: "p", classId: "a", sessions: 4, finished: 1 },
      { week: "2026-10-26", passageId: "p", classId: "a", sessions: 6, finished: 4 },
      { week: "2026-11-02", passageId: "p", classId: "b", sessions: 2, finished: 2 },
      { week: "2020-01-06", passageId: "p", classId: "a", sessions: 9, finished: 9 },
    ];
    const list = ["2026-10-26", "2026-11-02", "2026-11-09"];
    assert.deepEqual(weeklySeries(weeks, sums, { passageId: null, classId: null }, list).map((w) => w.sessions), [6, 4, 0]);
    assert.deepEqual(weeklySeries(weeks, sums, { passageId: null, classId: "b" }, list).map((w) => w.sessions), [0, 0, 0]);
  });
});

describe("readers", () => {
  test("the list is alphabetical by code, never by results", () => {
    const items = [{ code: "ZZZZ2222", sessions: [s("2026-11-01", 100)], words: {} }, { code: "AAAA2222", sessions: [s("2026-11-01", 5), s("2026-11-02", 5)], words: {} }];
    assert.deepEqual(listReaders(items).map((r) => [r.code, r.sessions]), [["AAAA2222", 2], ["ZZZZ2222", 1]]);
  });
  test("plain summaries, nothing judgmental", () => {
    assert.equal(readerSummary([s("a", 50)]), "Not enough sessions yet to show a pattern.");
    assert.equal(readerSummary([s("a", 40), s("b", 50), s("c", 70), s("d", 90)]), "Reading steadily more of the passage.");
    assert.equal(readerSummary([s("a", 90), s("b", 90), s("c", 70), s("d", 60)]).startsWith("Reading a little less"), true);
    assert.equal(readerSummary([s("a", 80), s("b", 82), s("c", 79), s("d", 81)]), "Reading about the same amount of the passage each time.");
    for (const text of [readerSummary([s("a", 10), s("b", 5)]), readerSummary([s("a", 5), s("b", 90)])]) assert.ok(!/poor|bad|fail|weak|behind|grade|rank/i.test(text));
  });
  test("a reader's detail orders sessions by day and lists only repeatedly missed words, with server-side text", () => {
    const items = [
      { code: "K7Q29XMA", passageId: "p1", sessions: [s("2026-11-03", 80, 2, 0), s("2026-11-01", 60, 3, 1)], words: { 2: { s: 2, d: 0 }, 1: { s: 1, d: 0 } } },
      { code: "OTHER222", passageId: "p1", sessions: [s("2026-11-02", 10)], words: { 0: { s: 9, d: 0 } } },
    ];
    const d = readerDetail(items, { code: "K7Q29XMA" }, textOf);
    assert.deepEqual(d.sessions.map((x) => [x.n, x.at, x.pct]), [[1, "2026-11-01", 60], [2, "2026-11-03", 80]]);
    assert.deepEqual(d.words, [{ word: "because", missed: 2 }]);
    assert.equal(JSON.stringify(d).includes("OTHER222"), false);
    assert.deepEqual(readerDetail(items, { code: "K7Q29XMA", passageId: "nope" }, textOf).sessions, []);
  });
});
