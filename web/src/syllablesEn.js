// English syllables. Hyphenation patterns (Liang's algorithm, the en-US patterns TeX uses) place breaks well for most words, but they are
// tuned for line breaks, not for how a word sounds: they leave short words whole (away, tiger), and follow spelling habits for some others.
// So the patterns run with relaxed minimums, a tidy-up step joins pieces that hold no vowel, and EXCEPTIONS below overrides common words
// known to come out wrong. Limit: words that are not in the list may still split at a spelling boundary instead of a sound boundary.
// The engine (hypher, BSD-3-Clause) and the patterns (hyphenation.en-us, from the TeX hyphenation project) are loaded on demand: see syllables.js.

/** Common words whose split is fixed by hand (lower case; "-" marks the break). Each one is checked by syllablesEn.test.js. */
export const EXCEPTIONS = {
  away: "a-way", again: "a-gain", ago: "a-go", alone: "a-lone", about: "a-bout", above: "a-bove", around: "a-round", across: "a-cross",
  tiger: "ti-ger", paper: "pa-per", robot: "ro-bot", open: "o-pen", over: "o-ver", never: "nev-er", river: "riv-er", seven: "sev-en",
  elephant: "el-e-phant", any: "an-y", many: "man-y", idea: "i-de-a", area: "ar-e-a", giant: "gi-ant", scary: "scar-y", okay: "o-kay",
  every: "ev-ery", everyone: "ev-ery-one", vegetable: "veg-e-ta-ble", chocolate: "choc-o-late", favorite: "fa-vor-ite", interesting: "in-ter-est-ing",
  wednesday: "wednes-day", february: "feb-ru-ar-y", dinosaur: "di-no-saur", camera: "cam-er-a",
  poem: "po-em", quiet: "qui-et", science: "sci-ence", lion: "li-on", violin: "vi-o-lin", video: "vid-e-o", radio: "ra-di-o", piano: "pi-an-o",
  yesterday: "yes-ter-day", tomorrow: "to-mor-row", together: "to-geth-er", potato: "po-ta-to", tomato: "to-ma-to", banana: "ba-nan-a",
};

const HAS_VOWEL = /[aeiouy]/i;

/** Joins every piece that has no vowel to its neighbour (the next piece, or the previous one at the end of the word). */
export function tidy(pieces) {
  const out = [];
  let carry = "";
  for (const piece of pieces) {
    const joined = carry + piece;
    if (HAS_VOWEL.test(joined)) {
      out.push(joined);
      carry = "";
    } else carry = joined;
  }
  if (carry) {
    if (out.length) out[out.length - 1] += carry;
    else out.push(carry);
  }
  return out;
}

/** Cut `original` at the same places as `lengths` (so capital letters survive). Falls back to one piece if the lengths do not fit. */
function sliceLike(original, lengths) {
  const chars = Array.from(original);
  if (lengths.reduce((a, b) => a + b, 0) !== chars.length) return [original];
  let at = 0;
  return lengths.map((n) => {
    const piece = chars.slice(at, at + n).join("");
    at += n;
    return piece;
  });
}

/**
 * @param Hypher the hypher constructor  @param patterns the en-us pattern set
 * @returns {(word: string) => string[]} syllables of one English word. Empty or odd input never throws.
 */
export function createEnglishSplitter(Hypher, patterns) {
  const engine = new Hypher({ ...patterns, leftmin: 1, rightmin: 2 });

  function splitPlain(word) {
    const lower = word.toLowerCase();
    const known = EXCEPTIONS[lower];
    if (known) return sliceLike(word, known.split("-").map((p) => Array.from(p).length));
    if (Array.from(word).length <= 3) return [word];
    try {
      return sliceLike(word, tidy(engine.hyphenate(lower)).map((p) => Array.from(p).length));
    } catch {
      return [word];
    }
  }

  return function split(input) {
    const word = typeof input === "string" ? input.trim() : "";
    if (!word) return [];
    if (/['’]/.test(word)) return [word]; // don't, it's: contractions are said as one beat
    if (word.includes("-")) return word.split("-").filter(Boolean).flatMap(split);
    if (!/^\p{L}+$/u.test(word)) return [word];
    return splitPlain(word);
  };
}
