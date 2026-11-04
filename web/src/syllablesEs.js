// Spanish syllables by rule. Spanish spelling is regular enough that a short rule set gets almost every word right (no data file needed).
// Rules: a vowel (or diphthong) is the core of a syllable; ch, ll and rr are single sounds; a consonant followed by l or r (pr, bl, tr ...)
// stays together; two strong vowels (a e o) or an accented weak vowel (í ú) next to another vowel are separate syllables (hiatus); a weak
// vowel (i u) next to another vowel makes a diphthong. "qu" and "gu" before e or i hold a silent u; "ü" makes the u sound.
// Limit: loanwords and prefix splits (sub-rayar) follow other rules, and Spain and Mexico split "tl" differently (at-las, a-tlas).

const STRONG = new Set("aeoáéóàèò");
const ACCENTED_WEAK = new Set("íú");
const STAY_TOGETHER = new Set(["pr", "pl", "br", "bl", "fr", "fl", "gr", "gl", "cr", "cl", "tr", "dr", "kr", "kl", "ch", "ll", "rr"]);

const isLetter = (c) => /\p{L}/u.test(c);

/** One kind per letter: "S" strong vowel, "W" weak vowel, "A" accented weak vowel, "C" consonant. */
function kindsOf(lower) {
  return lower.map((c, i) => {
    if (STRONG.has(c)) return "S";
    if (ACCENTED_WEAK.has(c)) return "A";
    if (c === "y") return i === lower.length - 1 && i > 0 ? "W" : "C"; // y is a vowel only at the end of a word
    if (c === "u" && (lower[i - 1] === "q" || (lower[i - 1] === "g" && "eéií".includes(lower[i + 1] ?? "")))) return "C"; // que, gui: silent u
    return "iuü".includes(c) ? "W" : "C";
  });
}

/** Letter positions where a new syllable starts. */
function cutPoints(lower, kinds) {
  const isVowel = (k) => k !== "C";
  const cuts = [];
  let i = 0;
  while (i < kinds.length) {
    if (!isVowel(kinds[i])) { i += 1; continue; }
    let j = i;
    while (j + 1 < kinds.length && isVowel(kinds[j + 1])) {
      const a = kinds[j];
      const b = kinds[j + 1];
      if ((a === "S" && b === "S") || a === "A" || b === "A") cuts.push(j + 1); // hiatus
      j += 1;
    }
    let k = j + 1;
    while (k < kinds.length && !isVowel(kinds[k])) k += 1;
    if (k >= kinds.length) break; // trailing consonants stay with the last syllable
    const between = k - (j + 1);
    if (between > 0) {
      if (between === 1) cuts.push(j + 1);
      else if (between === 2) cuts.push(STAY_TOGETHER.has(lower[j + 1] + lower[j + 2]) ? j + 1 : j + 2);
      else cuts.push(STAY_TOGETHER.has(lower[k - 2] + lower[k - 1]) ? k - 2 : k - 1);
    }
    i = k;
  }
  return cuts;
}

/** Syllables of one Spanish word, with the original letters. Empty or non-letter input gives [] or the text unchanged; never throws. */
export function splitSpanish(word) {
  const text = typeof word === "string" ? word : "";
  const chars = Array.from(text);
  if (chars.length === 0) return [];
  if (!chars.every(isLetter)) return [text];
  const lower = chars.map((c) => c.toLowerCase());
  const kinds = kindsOf(lower);
  if (kinds.every((k) => k === "C")) return [text];
  const cuts = [...new Set(cutPoints(lower, kinds))].sort((a, b) => a - b);
  const bounds = [0, ...cuts, chars.length];
  return bounds.slice(0, -1).map((start, n) => chars.slice(start, bounds[n + 1]).join(""));
}
