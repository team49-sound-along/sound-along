import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { MAX_FLAGS, parseReadAloudResult } from "../src/readAloud/parse.js";

const timing = { language: "en", words: Array.from({ length: 120 }, (_, i) => ({ i, text: i === 7 ? "..." : `word${i}` })) };
const ctx = { passageIds: new Set(["p1"]), classIds: new Set(["c1"]), timing };
const good = { passageId: "p1", classId: "c1", language: "en", wordsTotal: 100, wordsRead: 90, finished: false, retried: 1, words: [{ i: 3, kind: "skipped" }, { i: 9, kind: "differs" }] };
const status = (body, c = ctx) => {
  try {
    parseReadAloudResult(body, c);
    return 200;
  } catch (e) {
    return e.status;
  }
};

describe("parseReadAloudResult", () => {
  test("accepts a valid result and returns only the known fields", () => {
    assert.deepEqual(parseReadAloudResult(good, ctx), { ...good, readerCode: null });
  });
  test("a reader code is an opaque token of 8 to 12 safe characters, or absent", () => {
    assert.equal(parseReadAloudResult({ ...good, readerCode: "K7Q29XMA" }, ctx).readerCode, "K7Q29XMA");
    for (const code of ["short", "k7q29xma", "K7Q29XM0", "K7Q2 9XMA", "A".repeat(13), 12345678, "ANN LEE 1"]) assert.equal(status({ ...good, readerCode: code }), 400, String(code));
  });
  test("classId is optional and becomes null", () => {
    const { classId, ...rest } = good; // eslint-disable-line no-unused-vars
    assert.equal(parseReadAloudResult(rest, ctx).classId, null);
  });
  test("rejects unknown fields (no free text, no identifiers)", () => {
    for (const extra of [{ transcript: "hi" }, { name: "Ann" }, { deviceId: "x" }, { heard: "z" }]) assert.equal(status({ ...good, ...extra }), 400);
    assert.equal(status({ ...good, words: [{ i: 3, kind: "skipped", heard: "x" }] }), 400);
  });
  test("rejects wrong types, ranges and enums", () => {
    const bad = [
      { passageId: "nope" }, { classId: "nope" }, { classId: 5 }, { language: "fr" }, { language: "es" },
      { wordsTotal: 0 }, { wordsTotal: 1.5 }, { wordsTotal: "100" }, { wordsTotal: 121 }, { wordsRead: -1 }, { wordsRead: 101 },
      { finished: "yes" }, { retried: -1 }, { retried: 21 }, { retried: 1.5 }, { words: "x" }, { words: [null] },
      { words: [{ i: -1, kind: "skipped" }] }, { words: [{ i: 120, kind: "skipped" }] }, { words: [{ i: 1.5, kind: "skipped" }] },
      { words: [{ i: 1, kind: "other" }] }, { words: [{ i: 1 }] }, { words: [{ i: 7, kind: "skipped" }] },
      { words: [{ i: 1, kind: "skipped" }, { i: 1, kind: "skipped" }] },
    ];
    for (const patch of bad) assert.equal(status({ ...good, ...patch }), 400, JSON.stringify(patch));
    for (const body of ["x", [], null, 5]) assert.equal(status(body), 400);
  });
  test("finished must agree with the counts", () => {
    assert.equal(status({ ...good, wordsRead: 100, finished: true }), 200);
    assert.equal(status({ ...good, wordsRead: 100, finished: false }), 400);
    assert.equal(status({ ...good, wordsRead: 90, finished: true }), 400);
  });
  test("caps the list, and one position is not two kinds", () => {
    const many = Array.from({ length: MAX_FLAGS + 1 }, (_, i) => ({ i: i + 10, kind: "skipped" }));
    assert.equal(status({ ...good, words: many }), 400);
    assert.equal(status({ ...good, words: many.slice(0, MAX_FLAGS) }), 200);
    assert.equal(status({ ...good, words: [{ i: 3, kind: "skipped" }, { i: 3, kind: "differs" }] }), 400);
  });
  test("a missing timing document is a clean error", () => {
    assert.equal(status(good, { ...ctx, timing: null }), 400);
  });
});
