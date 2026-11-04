import { test } from "node:test";
import assert from "node:assert/strict";
import { splitSpanish } from "./syllablesEs.js";

const CASES = {
  // consonant groups: inseparable pairs stay together, others split
  construcción: "cons-truc-ción", transporte: "trans-por-te", instrumento: "ins-tru-men-to", abrazo: "a-bra-zo", biblioteca: "bi-blio-te-ca",
  comprar: "com-prar", cansado: "can-sa-do", también: "tam-bién", ejercicio: "e-jer-ci-cio", helicóptero: "he-li-cóp-te-ro",
  // ch, ll, rr are single sounds
  niño: "ni-ño", mucho: "mu-cho", calle: "ca-lle", perro: "pe-rro", guitarra: "gui-ta-rra", llave: "lla-ve",
  // silent u in que, qui, gue, gui; a pronounced u carries a diaeresis
  queso: "que-so", guitar: "gui-tar", pingüino: "pin-güi-no",
  // diphthongs: a weak vowel (i, u) next to another vowel stays in the same syllable
  escuela: "es-cue-la", aire: "ai-re", hielo: "hie-lo", ciudad: "ciu-dad", cuidado: "cui-da-do", ruido: "rui-do", veintiuno: "vein-tiu-no",
  muy: "muy", hoy: "hoy", buey: "buey", Uruguay: "U-ru-guay",
  // hiatus: two strong vowels, or an accented weak vowel, are separate syllables
  caer: "ca-er", poeta: "po-e-ta", teatro: "te-a-tro", león: "le-ón", país: "pa-ís", maíz: "ma-íz", día: "dí-a", río: "rí-o", baúl: "ba-úl",
  oído: "o-í-do", aéreo: "a-é-re-o",
  // silent h
  ahora: "a-ho-ra",
  // plain words
  está: "es-tá", casa: "ca-sa", mamá: "ma-má", gato: "ga-to", sol: "sol", yo: "yo", mañana: "ma-ña-na",
};

for (const [word, expected] of Object.entries(CASES)) {
  test(`splits ${word}`, () => assert.equal(splitSpanish(word).join("-"), expected));
}

test("keeps the original capital letters and accents", () => {
  assert.deepEqual(splitSpanish("Ñandú"), ["Ñan", "dú"]);
});

test("empty and odd input never throws", () => {
  assert.deepEqual(splitSpanish(""), []);
  assert.deepEqual(splitSpanish(null), []);
  assert.deepEqual(splitSpanish(undefined), []);
  assert.deepEqual(splitSpanish("123"), ["123"]);
  assert.deepEqual(splitSpanish("¿"), ["¿"]);
  assert.deepEqual(splitSpanish("xyz"), ["xyz"]);
});
