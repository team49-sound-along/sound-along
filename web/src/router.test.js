import { test } from "node:test";
import assert from "node:assert/strict";
import { parseHash } from "./router.js";

test("parses known routes", () => {
  assert.equal(parseHash("#/insights").name, "insights");
  assert.deepEqual(parseHash("#/read/abc-1").params, { id: "abc-1" });
});
test("query string is parsed", () => assert.equal(parseHash("#/assignments?passageId=x").query.passageId, "x"));
test("unknown or empty falls back to library", () => {
  assert.equal(parseHash("").name, "library");
  assert.equal(parseHash("#/nope").name, "library");
  assert.equal(parseHash("#/read").name, "library");
});

import { isTeacherOnly } from "./router.js";
test("teacher screens parse and are guarded", () => {
  for (const n of ["settings", "pronunciations", "review"]) {
    assert.equal(parseHash(`#/${n}`).name, n);
    assert.equal(isTeacherOnly(n), true);
  }
  assert.equal(parseHash("#/pronunciations?word=gaieties").query.word, "gaieties");
  assert.equal(isTeacherOnly("library"), false);
  assert.equal(isTeacherOnly("generate"), false);
});

test("listening test route exists and is open to both roles", () => {
  assert.equal(parseHash("#/listening").name, "listening");
  assert.equal(isTeacherOnly("listening"), false);
});

test("the practice screen is a route with a passage id, and a missing id falls back to the library", async () => {
  const { parseHash } = await import("./router.js");
  assert.deepEqual(parseHash("#/practice/abc"), { name: "practice", params: { id: "abc" }, query: {} });
  assert.equal(parseHash("#/practice").name, "library");
});

test("My words and the Voice section routes", async () => {
  const { VOICE_SECTION } = await import("./router.js");
  assert.equal(parseHash("#/words").name, "words");
  assert.equal(isTeacherOnly("words"), false);
  assert.deepEqual(VOICE_SECTION, ["settings", "pronunciations", "review", "listening"]);
});
