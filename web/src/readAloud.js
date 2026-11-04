// Follows a learner reading a passage aloud. Pure logic: no DOM, no Vue, no recognizer. Any speech engine can feed it.
//
// Input: the passage words and a stream of recognizer results { id, transcript, isFinal }. `id` names one stretch of speech; the same id
// arrives again with a longer or revised transcript (interim results) until it is final. Output: events
//   advance { index }          a word was read (exact or close enough)
//   skipped { index, indexes } words were passed over: the following words were heard but these were not. Listening stops.
//   differs { index, heard }   a word was clearly heard as a different word. Listening stops.
//   done                       the last word was read
// State is never changed in place: feed() returns a new state. Child-friendly by design: close spellings, accents, repeats, fillers, stray
// noise and merged or split words are all tolerated, and sounds are never scored. Only whole-word differences are reported.
import { digitsFor, spellNumber } from "./numberWords.js";

export const LOOKAHEAD = 4; // how many words ahead a heard word may match when the current word was not heard
export const STABLE_TAIL = 3; // an interim result's last words may still change: a mismatch is judged only with this many words after it
export const REPEAT_WINDOW = 3; // heard words matching one of this many words just read are repeats, not errors
export const CLOSE = 0.6; // edit-distance similarity that counts as the same word (words of 4+ letters)
export const MERGE = 0.85; // similarity for two heard words standing for one expected word, or the reverse
const PLAUSIBLE = 0.34; // below this a heard word is not even an attempt at the expected word, so it is treated as noise

const FILLERS = {
  en: new Set(["um", "uh", "uhm", "er", "erm", "hmm", "hm", "mm", "mmm", "ah", "eh"]),
  es: new Set(["eh", "em", "mm", "mmm", "ah", "ehh", "hmm", "este"]),
};

const lang = (language) => (language === "es" ? "es" : "en");

/** Lower case, no punctuation, no apostrophes or hyphens, accents folded. Spanish keeps the tilde on n (año is not ano). */
export function normalizeWord(text, language = "en") {
  let s = String(text ?? "").toLowerCase().normalize("NFD");
  s = s.replace(lang(language) === "es" ? /[̀-̂̄-ͯ]/g : /[̀-ͯ]/g, "");
  return s.normalize("NFC").replace(/[^\p{L}\p{N}]/gu, "");
}

export function editDistance(a, b) {
  const x = Array.from(a);
  const y = Array.from(b);
  let prev = Array.from({ length: y.length + 1 }, (_, j) => j);
  x.forEach((cx, i) => {
    const row = [i + 1];
    y.forEach((cy, j) => row.push(Math.min(prev[j + 1] + 1, row[j] + 1, prev[j] + (cx === cy ? 0 : 1))));
    prev = row;
  });
  return prev[y.length];
}

export function similarity(a, b) {
  if (a === b) return 1;
  const longest = Math.max(Array.from(a).length, Array.from(b).length);
  return longest === 0 ? 1 : 1 - editDistance(a, b) / longest;
}

/** Accepted spellings of one expected word: itself, plus digits or number words where it is a number. A number we cannot spell is lenient. */
function formsOf(norm, language) {
  if (/^\d+$/.test(norm)) {
    const spelled = spellNumber(norm, language);
    return spelled ? { forms: [norm, spelled], lenient: false } : { forms: [norm], lenient: true };
  }
  const digits = digitsFor(norm, language);
  return { forms: digits ? [norm, digits] : [norm], lenient: false };
}

function closeEnough(heard, form) {
  const shortest = Math.min(heard.length, form.length);
  if (shortest < 3) return false;
  const plural = [heard + "s", heard + "es"].includes(form) || [form + "s", form + "es"].includes(heard);
  return plural || (shortest >= 4 && similarity(heard, form) >= CLOSE);
}

/** 2 = exact, 1 = close enough, 0 = different. */
function quality(heard, target) {
  if (target.lenient) return heard ? 1 : 0;
  if (target.forms.includes(heard)) return 2;
  return target.forms.some((f) => closeEnough(heard, f)) ? 1 : 0;
}

const joinedMatches = (a, b, target) => {
  const joined = a + b;
  return target.forms.some((f) => joined === f || (joined.length >= 5 && similarity(joined, f) >= MERGE));
};
const splitMatches = (heard, target, next) => {
  const joined = target.norm + next.norm;
  return heard === joined || (heard.length >= 5 && similarity(heard, joined) >= MERGE);
};

const wordText = (w) => (typeof w === "string" ? w : String(w?.text ?? ""));

export function createReadAlong(words, { language = "en" } = {}) {
  const lg = lang(language);
  const targets = (Array.isArray(words) ? words : [])
    .map((w, i) => {
      const norm = normalizeWord(wordText(w), lg);
      return { index: Number.isInteger(w?.i) ? w.i : i, text: wordText(w), norm, ...formsOf(norm, lg) };
    })
    .filter((t) => t.norm !== "");
  return { language: lg, targets, cursor: 0, seen: {}, len: {}, read: {}, skippedEver: [], differsEver: [], retries: 0, pending: null, halted: null, done: false };
}

export const cursorIndex = (state) => state.targets[state.cursor]?.index ?? null;

const tokenize = (transcript, lg) => transcript.split(/\s+/).map((t) => normalizeWord(t, lg)).filter(Boolean);

/** Finds the nearest later word that the heard word matches and that the next heard word confirms. */
function lookahead(tokens, p, targets, cursor) {
  const heard = tokens[p];
  const next = tokens[p + 1];
  for (let k = 1; k <= LOOKAHEAD && cursor + k < targets.length; k += 1) {
    const j = cursor + k;
    const q = quality(heard, targets[j]);
    if (q === 0) continue;
    const lastWord = j === targets.length - 1;
    if (lastWord && (q === 2 || heard.length >= 4)) return { k, confirmed: true };
    if (next !== undefined && !lastWord && quality(next, targets[j + 1]) > 0) return { k, confirmed: true };
    if (next === undefined && q === 2 && heard.length >= 5) return { k, confirmed: false };
  }
  return null;
}

function run(state, tokens, start, final) {
  const { targets } = state;
  const n = tokens.length;
  const resolveLimit = final ? n : n - STABLE_TAIL;
  const events = [];
  const read = { ...state.read };
  const skippedEver = [...state.skippedEver];
  const differsEver = [...state.differsEver];
  let { cursor, pending } = state;
  let halted = null;
  let p = start;

  const advance = (count, how) => {
    for (let j = 0; j < count; j += 1) {
      read[targets[cursor].index] = true;
      events.push({ type: "advance", index: targets[cursor].index, quality: how });
      cursor += 1;
    }
    pending = null;
  };
  const stop = (event) => {
    events.push(event);
    halted = { type: event.type, index: event.index };
  };

  while (p < n && cursor < targets.length && !halted) {
    const heard = tokens[p];
    const target = targets[cursor];
    const q = quality(heard, target);
    if (q === 2) { advance(1, "exact"); p += 1; continue; }
    if (p + 1 < n && joinedMatches(heard, tokens[p + 1], target)) { advance(1, "exact"); p += 2; continue; }
    if (cursor + 1 < targets.length && splitMatches(heard, target, targets[cursor + 1])) { advance(2, "close"); p += 1; continue; }
    if (q === 1 && (final || p < n - 1)) { advance(1, "close"); p += 1; continue; }
    if (p >= resolveLimit) break; // not enough words after this one to judge it yet

    if (FILLERS[state.language].has(heard)) { p += 1; continue; }
    const ahead = lookahead(tokens, p, targets, cursor);
    if (ahead) {
      if (pending && ahead.k === 1) {
        differsEver.push(target.index);
        stop({ type: "differs", index: target.index, heard: pending.heard, expected: target.text });
      } else {
        const skipped = targets.slice(cursor, cursor + ahead.k);
        skipped.forEach((t) => skippedEver.push(t.index));
        stop({ type: "skipped", index: target.index, indexes: skipped.map((t) => t.index), word: target.text, words: skipped.map((t) => t.text) });
      }
      pending = null;
      break;
    }
    const repeated = Array.from({ length: REPEAT_WINDOW }, (_, r) => targets[cursor - 1 - r]).some((t) => t && quality(heard, t) > 0);
    if (repeated) { p += 1; continue; }
    const next = tokens[p + 1];
    if (next === undefined) {
      if (similarity(heard, target.norm) >= PLAUSIBLE) pending = { heard };
      p += 1;
    } else if (quality(next, target) > 0) {
      p += 1; // a false start: the right word follows
    } else if (cursor + 1 < targets.length && quality(next, targets[cursor + 1]) > 0) {
      differsEver.push(target.index);
      stop({ type: "differs", index: target.index, heard, expected: target.text });
    } else {
      p += 1; // unrelated noise or talk
    }
  }

  const finished = cursor >= targets.length;
  if (finished) events.push({ type: "done" });
  return { events, cursor, pending, read, skippedEver, differsEver, halted, done: finished, consumed: final || halted || finished ? n : p };
}

/** Feeds one recognizer result. Returns { state, events }; the old state is untouched. */
export function feed(state, result) {
  if (!state || !result || typeof result.transcript !== "string") return { state, events: [] };
  const id = String(result.id ?? 0);
  const tokens = tokenize(result.transcript, state.language);
  const len = { ...state.len, [id]: tokens.length };
  if (state.halted || state.done || state.targets.length === 0) return { state: { ...state, len }, events: [] };
  const { events, consumed, ...rest } = run(state, tokens, state.seen[id] ?? 0, result.isFinal === true);
  return { state: { ...state, ...rest, len, seen: { ...state.seen, [id]: consumed } }, events };
}

/**
 * "Read from here": continue at a word index (the first spoken word at or after it). Speech already heard is not replayed, and words from
 * there on count as unread until they are read again. `retry: false` is for carrying on after a pause, which is not a retry.
 */
export function restartFrom(state, wordIndex, { retry = true } = {}) {
  if (state.targets.length === 0) return { ...state, cursor: 0, read: {}, pending: null, halted: null }; // nothing to read from: stay put
  const at = state.targets.findIndex((t) => t.index >= wordIndex);
  const cursor = at >= 0 ? at : Math.max(0, state.targets.length - 1);
  const read = Object.fromEntries(Object.entries(state.read).filter(([index]) => Number(index) < state.targets[cursor].index));
  return { ...state, cursor, read, seen: { ...state.len }, pending: null, halted: null, done: false, retries: state.retries + (retry ? 1 : 0) };
}

/** Counts for the end-of-practice summary. Words are counted once however many times they were read. */
export function summarize(state) {
  const unique = (list) => new Set(list).size;
  return {
    total: state.targets.length,
    read: Object.keys(state.read).length,
    skipped: unique(state.skippedEver),
    heardDifferently: unique(state.differsEver),
    retried: state.retries,
  };
}
