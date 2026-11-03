import { test } from "node:test";
import assert from "node:assert/strict";
import { DEFAULTS, loadPrefs, prefsToCssVars, sanitizePrefs, savePrefs, updatePref } from "./readingPrefs.js";

const memoryStorage = (initial = {}) => {
  const data = { ...initial };
  return {
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
    dump: () => ({ ...data }),
  };
};
const brokenStorage = {
  getItem() { throw new Error("blocked"); },
  setItem() { throw new Error("blocked"); },
};

test("defaults follow the research: large text, roomy spacing, word highlight, phrase breaks on", () => {
  assert.deepEqual(DEFAULTS, { size: "large", font: "standard", spacing: "roomy", highlight: "words", phraseBreaks: true, reduceMotion: false });
});

test("sanitize keeps valid values and replaces invalid ones with defaults", () => {
  const result = sanitizePrefs({ size: "huge", font: "comic", spacing: "roomy", highlight: "sentences", phraseBreaks: "yes", reduceMotion: true, extra: 1 });
  assert.deepEqual(result, { size: "huge", font: "standard", spacing: "roomy", highlight: "sentences", phraseBreaks: true, reduceMotion: true });
});

test("sanitize handles non-objects", () => {
  for (const bad of [null, undefined, 5, "x", []]) assert.deepEqual(sanitizePrefs(bad), DEFAULTS);
});

test("css variables map each choice", () => {
  const vars = prefsToCssVars({ ...DEFAULTS, size: "xl", spacing: "extra", font: "atkinson" });
  assert.equal(vars["--read-size"], "34px");
  assert.equal(vars["--read-ls"], "0.07em");
  assert.equal(vars["--read-ws"], "0.22em");
  assert.equal(vars["--read-lh"], "2");
  assert.match(vars["--read-font"], /Atkinson Hyperlegible/);
});

test("css variables fall back to defaults for bad input", () => {
  assert.equal(prefsToCssVars({ size: "nope" })["--read-size"], "28px");
});

test("updatePref returns a new object and never mutates the old one", () => {
  const before = { ...DEFAULTS };
  const after = updatePref(before, "size", "huge");
  assert.equal(after.size, "huge");
  assert.equal(before.size, "large");
  assert.notEqual(after, before);
});

test("updatePref ignores unknown keys and invalid values", () => {
  assert.deepEqual(updatePref(DEFAULTS, "size", "gigantic"), DEFAULTS);
  assert.deepEqual(updatePref(DEFAULTS, "colour", "red"), DEFAULTS);
});

test("save then load round-trips", () => {
  const storage = memoryStorage();
  assert.equal(savePrefs(storage, { ...DEFAULTS, highlight: "off" }), true);
  assert.equal(loadPrefs(storage).highlight, "off");
});

test("load survives missing, corrupt and blocked storage", () => {
  assert.deepEqual(loadPrefs(memoryStorage()), DEFAULTS);
  assert.deepEqual(loadPrefs(memoryStorage({ "soundalong.reading": "{not json" })), DEFAULTS);
  assert.deepEqual(loadPrefs(brokenStorage), DEFAULTS);
  assert.deepEqual(loadPrefs(undefined), DEFAULTS);
});

test("save reports failure instead of throwing", () => {
  assert.equal(savePrefs(brokenStorage, DEFAULTS), false);
  assert.equal(savePrefs(undefined, DEFAULTS), false);
});
