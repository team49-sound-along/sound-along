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
