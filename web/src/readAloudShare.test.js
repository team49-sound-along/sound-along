import assert from "node:assert/strict";
import { test } from "node:test";
import { createReadAlong } from "./readAloud.js";
import { MAX_FLAGS, buildSharePayload, readAloudSettingsFor } from "./readAloudShare.js";
import { ALPHABET, CODE_PATTERN, makeReaderCode, readerCode, readerLabel, startNewReaderCode } from "./readerCode.js";

const words = (n) => Array.from({ length: n }, (_, i) => ({ i: i + 100, text: `word${String.fromCharCode(97 + (i % 26))}${i}` }));
const stateWith = (n, patch) => ({ ...createReadAlong(words(n)), ...patch });
const memory = () => {
  const m = new Map();
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v), removeItem: (k) => m.delete(k) };
};

test("the payload has only counts and positions, with the passage's own word indexes", () => {
  const state = stateWith(10, { read: { 100: true, 101: true, 102: true }, skippedEver: [105, 103, 103], differsEver: [104, 105], retries: 2 });
  assert.deepEqual(buildSharePayload({ passageId: "p", classId: "c", language: "en", state }), {
    passageId: "p", classId: "c", language: "en", wordsTotal: 10, wordsRead: 3, finished: false, retried: 2,
    words: [{ i: 103, kind: "skipped" }, { i: 105, kind: "skipped" }, { i: 104, kind: "differs" }],
  });
});

test("no class and no reader code leave those fields out; finished is read === total; flags are capped", () => {
  const read = Object.fromEntries(words(60).map((w) => [w.i, true]));
  const many = Array.from({ length: 80 }, (_, i) => i + 100);
  const payload = buildSharePayload({ passageId: "p", language: "es", state: stateWith(60, { read, skippedEver: many }) });
  assert.equal(payload.finished, true);
  assert.equal(payload.language, "es");
  assert.equal(payload.words.length, MAX_FLAGS);
  assert.deepEqual(Object.keys(payload).sort(), ["finished", "language", "passageId", "retried", "words", "wordsRead", "wordsTotal"]);
});

test("nothing heard is ever in the payload", () => {
  const state = stateWith(5, { differsEver: [101], pending: { heard: "secret words" } });
  assert.ok(!JSON.stringify(buildSharePayload({ passageId: "p", language: "en", state })).includes("secret"));
});

test("a reader code is added only when given; an empty passage shares nothing", () => {
  assert.equal(buildSharePayload({ passageId: "p", language: "en", state: stateWith(3), readerCode: "K7Q29XMA" }).readerCode, "K7Q29XMA");
  assert.equal(buildSharePayload({ passageId: "p", language: "en", state: stateWith(0) }), null);
});

test("settings for a class fall back to the default, and a missing view means nothing is on", () => {
  const view = { defaults: { mic: true, share: true, readers: false }, classes: [{ id: "c", mic: false, share: true, readers: true }] };
  assert.deepEqual(readAloudSettingsFor(view, "c"), { mic: false, share: true, readers: true });
  assert.deepEqual(readAloudSettingsFor(view, "other"), { mic: true, share: true, readers: false });
  assert.deepEqual(readAloudSettingsFor(view, undefined), { mic: true, share: true, readers: false });
  assert.deepEqual(readAloudSettingsFor(null, "c"), { mic: false, share: false, readers: false });
});

test("reader codes: random, safe letters, kept on this device only, renewable", () => {
  const code = makeReaderCode();
  assert.match(code, CODE_PATTERN);
  assert.ok([...code].every((c) => ALPHABET.includes(c)));
  assert.notEqual(makeReaderCode(), makeReaderCode());
  const storage = memory();
  const first = readerCode(storage);
  assert.equal(readerCode(storage), first);
  const second = startNewReaderCode(storage);
  assert.notEqual(second, first);
  assert.equal(readerCode(storage), second);
  assert.equal(readerLabel("K7Q29XMA"), "Reader K7Q2 9XMA");
});

test("reader code bytes at the bias limit are skipped so letters stay equally likely", () => {
  const bytes = [...Array(16)].map(() => 255).concat([...Array(16)].map((_, i) => i));
  let call = 0;
  const code = makeReaderCode(() => (call++ === 0 ? Uint8Array.from(bytes.slice(0, 16)) : Uint8Array.from(bytes.slice(16))));
  assert.equal(code, ALPHABET.slice(0, 8));
});

test("blocked storage gives no code and a corrupt saved value is replaced", () => {
  const blocked = { getItem() { throw new Error("no"); }, setItem() { throw new Error("no"); }, removeItem() {} };
  assert.equal(readerCode(blocked), null);
  assert.equal(readerCode(null), null);
  const bad = memory();
  bad.setItem("soundalong.readerCode.v1", "ann lee");
  assert.match(readerCode(bad), CODE_PATTERN);
});
