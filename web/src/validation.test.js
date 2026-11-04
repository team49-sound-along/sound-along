import { test } from "node:test";
import assert from "node:assert/strict";
import { validateGenerate, generateErrorMessage } from "./validation.js";

const text = "x".repeat(50);
test("valid input passes", () => assert.equal(validateGenerate({ title: "Cats", text }).valid, true));
test("blank title and short text fail", () => {
  const r = validateGenerate({ title: "  ", text: "short" });
  assert.ok(r.errors.title && r.errors.text);
});
test("limits are enforced", () => {
  assert.ok(validateGenerate({ title: "a".repeat(121), text }).errors.title);
  assert.ok(validateGenerate({ title: "ok", text: "x".repeat(100001) }).errors.text);
  assert.equal(validateGenerate({ title: "a".repeat(120), text: "x".repeat(100000) }).valid, true);
  const manyWords = Array.from({ length: 12001 }, () => "go").join(" ");
  assert.match(validateGenerate({ title: "ok", text: manyWords }).errors.text, /most that can be made at once/);
  assert.equal(validateGenerate({ title: "a", text: "x".repeat(20) }).valid, true);
});
test("friendly messages for 429 and 503", () => {
  assert.match(generateErrorMessage(429), /Too many/);
  assert.match(generateErrorMessage(503), /turned off/);
  assert.equal(generateErrorMessage(400, "Bad title"), "Bad title");
});
