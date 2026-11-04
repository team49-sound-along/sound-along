// Spelled-out numbers, already normalized (lower case, no spaces or accents), so "21" and "twenty one" can be compared.
// English covers 0 to 100; Spanish covers 0 to 30 and the tens (larger Spanish numbers are written with several words).
const EN_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"];
const EN_TENS = { 20: "twenty", 30: "thirty", 40: "forty", 50: "fifty", 60: "sixty", 70: "seventy", 80: "eighty", 90: "ninety" };
const ES_SMALL = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce", "trece", "catorce", "quince", "dieciseis", "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidos", "veintitres", "veinticuatro", "veinticinco", "veintiseis", "veintisiete", "veintiocho", "veintinueve", "treinta"];
const ES_TENS = { 40: "cuarenta", 50: "cincuenta", 60: "sesenta", 70: "setenta", 80: "ochenta", 90: "noventa", 100: "cien" };

function englishTable() {
  const table = {};
  for (let n = 0; n <= 100; n += 1) {
    if (n < 20) table[n] = EN_ONES[n];
    else if (n === 100) table[n] = "onehundred";
    else table[n] = EN_TENS[Math.floor(n / 10) * 10] + (n % 10 ? EN_ONES[n % 10] : "");
  }
  return table;
}

function spanishTable() {
  return { ...ES_TENS, ...Object.fromEntries(ES_SMALL.map((word, n) => [n, word])) };
}

const TABLES = { en: englishTable(), es: spanishTable() };
const REVERSE = Object.fromEntries(Object.entries(TABLES).map(([lg, t]) => [lg, Object.fromEntries(Object.entries(t).map(([n, w]) => [w, n]))]));

/** Spelled form of a whole number ("21" gives "twentyone"), or null when the app cannot spell it. */
export const spellNumber = (digits, language) => (TABLES[language] ?? TABLES.en)[Number(digits)] ?? null;

/** Digits for a spelled number ("twentyone" gives "21"), or null. */
export const digitsFor = (word, language) => (REVERSE[language] ?? REVERSE.en)[word] ?? null;
