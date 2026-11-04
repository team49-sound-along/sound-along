import { test } from "node:test";
import assert from "node:assert/strict";
import { analyzeMix, keepLanguage } from "./languageMix.js";

const ES = "Platero es un burro pequeño, peludo y suave; tan blando por fuera que se diría todo de algodón, y los niños lo quieren mucho cuando pasa por la calle.";
const EN = "Platero is a small, hairy and soft donkey, so gentle on the outside that he seems to be made of cotton, and the children love him when he passes in the street.";
const Q = "Do you like oranges and what is your favorite fruit?";

test("a text in one language is not mixed", () => {
  const m = analyzeMix([ES, ES, ES].join("\n\n"));
  assert.equal(m.mixed, false);
  assert.equal(m.majority, null);
});

test("a text with a real share of the other language is mixed and says which is the majority", () => {
  const m = analyzeMix([ES, ES, EN, ES, EN, ES].join("\n\n"));
  assert.equal(m.mixed, true);
  assert.equal(m.majority, "es");
  assert.equal(m.minority, "en");
});

test("a couple of stray English words inside a Spanish text do not count as a mix", () => {
  const m = analyzeMix([ES, "Hello.", ES, ES, ES, ES].join("\n\n"));
  assert.equal(m.mixed, false);
});

test("short paragraphs are classified too (a comprehension question in English)", () => {
  const m = analyzeMix([ES, Q, ES].join("\n\n"));
  assert.equal(m.paragraphs[1].lang, "en");
});

test("keeping one language removes the paragraphs of the other and keeps headings whose language is unclear", () => {
  const text = ["# CHAPTER I", ES, Q, EN, ES].join("\n\n");
  const kept = keepLanguage(text, "es");
  assert.ok(kept.includes("CHAPTER I") && kept.includes("Platero es un burro"));
  assert.ok(!kept.includes("Do you like oranges") && !kept.includes("Platero is a small"));
  assert.equal(kept.split("\n\n").length, 3);
});

test("empty and whitespace-only text is harmless", () => {
  assert.equal(analyzeMix("").mixed, false);
  assert.equal(analyzeMix("   \n\n  ").paragraphs.length, 0);
  assert.equal(keepLanguage("", "en"), "");
});
