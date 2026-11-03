import { test } from "node:test";
import assert from "node:assert/strict";
import { isSpanish, langAttr, languageCopy, voicesFor, withLanguage } from "./language.js";

test("language detection defaults to English", () => {
  assert.equal(isSpanish({ language: "es" }), true);
  assert.equal(isSpanish({ language: "en" }), false);
  assert.equal(isSpanish({}), false);
  assert.equal(isSpanish(undefined), false);
  assert.equal(langAttr("es"), "es");
  assert.equal(langAttr(undefined), "en");
  assert.equal(langAttr("fr"), "en");
});
test("voices split by lang, missing lang counts as English", () => {
  const v = [{ id: "a", lang: "en" }, { id: "b", lang: "es" }, { id: "c" }];
  assert.deepEqual(voicesFor(v, "en").map((x) => x.id), ["a", "c"]);
  assert.deepEqual(voicesFor(v, "es").map((x) => x.id), ["b"]);
  assert.deepEqual(voicesFor(undefined, "es"), []);
});
test("copy is Spanish-friendly for es", () => {
  assert.match(languageCopy("es").textPlaceholder, /español/);
  assert.equal(languageCopy("en").textPlaceholder, "");
});
test("withLanguage adds the field without mutating", () => {
  const body = { title: "t" };
  assert.deepEqual(withLanguage(body, "es"), { title: "t", language: "es" });
  assert.deepEqual(body, { title: "t" });
  assert.equal(withLanguage(body, "xx").language, "en");
});
