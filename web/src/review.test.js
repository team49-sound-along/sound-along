import { test } from "node:test";
import assert from "node:assert/strict";
import { dismissWord, fixHref, suspectCount } from "./review.js";

const items = [
  { passageId: "p1", title: "One", suspects: [{ expected: "colour", heard: "color" }, { expected: "gaieties", heard: "deities" }] },
  { passageId: "p2", title: "Two", suspects: [{ expected: "colour", heard: "collar" }] },
];
test("dismiss removes the word everywhere and drops empty passages", () => {
  const next = dismissWord(items, "colour");
  assert.deepEqual(next.map((i) => i.passageId), ["p1"]);
  assert.equal(suspectCount(next), 1);
  assert.equal(items.length, 2);
});
test("fixHref encodes", () => assert.equal(fixHref("o'clock"), "#/pronunciations?word=o'clock"));
