// "Words to practice": the words the follower flagged (skipped or heard differently) in this reading, and adding them to My words.
// Pure and immutable. Saved only on this device through practice.js; no word and no result is sent anywhere.
import { wordKey } from "./cards.js";
import { emptyState } from "./practice.js";

/** @returns {{ index: number, text: string, key: string }[]} flagged words, once per spelling, in passage order */
export function wordsToPractice(follower, words) {
  if (!follower || !Array.isArray(words)) return [];
  const flagged = new Set([...(follower.skippedEver ?? []), ...(follower.differsEver ?? [])]);
  const seen = new Set();
  const list = [];
  words.forEach((w, position) => {
    const index = Number.isInteger(w?.i) ? w.i : position;
    const key = wordKey(w?.text);
    if (!flagged.has(index) || !key || seen.has(key)) return;
    seen.add(key);
    list.push({ index, text: String(w.text).replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, ""), key });
  });
  return list;
}

const keysOf = (items) => (Array.isArray(items) ? items : []).map((w) => w?.key).filter((k) => typeof k === "string" && k !== "");

/** Stars every word. A word already in My words is left exactly as it is (it keeps its place in the review schedule). */
export function addAllToMyWords(state, items, now) {
  const current = state ?? emptyState();
  const added = Object.fromEntries(keysOf(items).filter((k) => !current.words[k]).map((k) => [k, { box: 0, due: now }]));
  return { words: { ...current.words, ...added } };
}

/** How many of these words are not in My words yet. */
export function countNew(state, items) {
  const have = state?.words ?? {};
  return new Set(keysOf(items).filter((k) => !have[k])).size;
}
