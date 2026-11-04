import { test } from "node:test";
import assert from "node:assert/strict";
import { guessLanguage } from "./languageGuess.js";

const EN = "The red fox ran across the green field and the children watched it from the hill. It was a bright afternoon and they were all very happy that the day had come.";
const ES = "El zorro rojo corrió por el campo verde y los niños lo miraban desde la colina. Era una tarde clara y todos estaban muy felices de que el día había llegado.";

test("the language of pasted text is recognised only when the evidence is clear", () => {
  assert.equal(guessLanguage(EN), "en");
  assert.equal(guessLanguage(ES), "es");
  assert.equal(guessLanguage("Hola"), null);
  assert.equal(guessLanguage(`${EN} ${ES}`), null);
  assert.equal(guessLanguage(undefined), null);
});
