import assert from "node:assert/strict";
import { test } from "node:test";
import { filterLibrary, hasAiVoice, hasHumanVoice } from "./libraryFilters.js";
import { groupVariants } from "./voices.js";

const raw = [
  { id: "a", title: "The Water Cycle", engine: "polly", language: "en", pairId: "a-h" },
  { id: "a-h", title: "The Water Cycle", engine: "human", language: "en", pairId: "a" },
  { id: "b", title: "El Gato", engine: "polly", language: "es" },
  { id: "c", title: "Moon Walk", engine: "human", language: "en" },
  { id: "d", title: "Bees", engine: "polly" },
];
const grouped = groupVariants(raw);
const ids = (list) => list.map((p) => p.id);

test("no filters returns every passage", () => {
  assert.deepEqual(ids(filterLibrary(grouped, {})), ["a", "b", "c", "d"]);
  assert.deepEqual(ids(filterLibrary(grouped)), ["a", "b", "c", "d"]);
});

test("search matches titles case-insensitively and ignores surrounding spaces", () => {
  assert.deepEqual(ids(filterLibrary(grouped, { query: "  WATER " })), ["a"]);
});

test("voice filter: human recording includes paired and standalone human passages", () => {
  assert.deepEqual(ids(filterLibrary(grouped, { voice: "human" })), ["a", "c"]);
});

test("voice filter: AI voice includes passages with an AI variant, not human-only ones", () => {
  assert.deepEqual(ids(filterLibrary(grouped, { voice: "ai" })), ["a", "b", "d"]);
});

test("language filter treats a missing language as English", () => {
  assert.deepEqual(ids(filterLibrary(grouped, { language: "es" })), ["b"]);
  assert.deepEqual(ids(filterLibrary(grouped, { language: "en" })), ["a", "c", "d"]);
  assert.deepEqual(ids(filterLibrary(grouped, { language: "all" })), ["a", "b", "c", "d"]);
});

test("filters combine", () => {
  assert.deepEqual(ids(filterLibrary(grouped, { voice: "human", language: "en", query: "moon" })), ["c"]);
});

test("returns an empty list when nothing matches and does not mutate the input", () => {
  const copy = JSON.stringify(grouped);
  assert.deepEqual(filterLibrary(grouped, { query: "zzz" }), []);
  assert.equal(JSON.stringify(grouped), copy);
});

test("tolerates missing fields and non-array input", () => {
  const odd = [{ id: "x" }, { id: "y", title: null, engine: undefined }];
  assert.deepEqual(ids(filterLibrary(odd, { query: "" })), ["x", "y"]);
  assert.deepEqual(filterLibrary(odd, { query: "a" }), []);
  assert.deepEqual(ids(filterLibrary(odd, { voice: "ai" })), ["x", "y"]);
  assert.deepEqual(filterLibrary(null, { query: "a" }), []);
  assert.deepEqual(ids(filterLibrary(grouped, { voice: "bogus", language: "bogus" })), ["a", "b", "c", "d"]);
});

test("voice predicates", () => {
  assert.equal(hasHumanVoice({ engine: "human" }), true);
  assert.equal(hasHumanVoice({ engine: "polly", humanId: "h" }), true);
  assert.equal(hasHumanVoice({ engine: "polly" }), false);
  assert.equal(hasAiVoice({ engine: "human" }), false);
  assert.equal(hasAiVoice({}), true);
  assert.equal(hasHumanVoice(null), false);
});
