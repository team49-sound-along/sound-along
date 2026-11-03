// Pure timing helpers for the read-along reader. No DOM, no Vue: easy to test.

/**
 * Index of the word being spoken at `ms`, or -1 before the first word.
 * `words` is sorted by start_ms. Between two words (a pause) the earlier word stays active,
 * so highlights never flicker off during short gaps.
 */
export function findActiveIndex(words, ms) {
  if (!words.length || ms < words[0].start_ms) return -1;
  let lo = 0;
  let hi = words.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (words[mid].start_ms <= ms) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

/** Seek target in seconds for a tapped word index; clamps bad input. */
export function seekSeconds(words, index) {
  if (!Number.isInteger(index) || index < 0 || index >= words.length) return 0;
  return words[index].start_ms / 1000;
}

/** Validate a timing array; returns a list of human-readable problems (empty if fine). */
export function validateTiming(words) {
  const problems = [];
  words.forEach((w, n) => {
    if (w.i !== n) problems.push(`word ${n}: index ${w.i} is not contiguous`);
    if (!(w.end_ms >= w.start_ms)) problems.push(`word ${n}: end before start`);
    if (n > 0 && w.start_ms < words[n - 1].start_ms) problems.push(`word ${n}: starts before previous word`);
  });
  return problems;
}

/**
 * Playback window for "Hear this word": start a little before the word and stop a little after it.
 * Returns {startSec, endSec}, or null when the word is missing or its time is only estimated (aligned === false),
 * because an estimated slice would cut the word off or play its neighbours.
 */
export function wordSlice(words, index, { padBeforeMs = 40, padAfterMs = 80 } = {}) {
  if (!Number.isInteger(index) || index < 0 || index >= words.length) return null;
  const w = words[index];
  if (w.aligned === false) return null;
  if (!Number.isFinite(w.start_ms) || !Number.isFinite(w.end_ms)) return null;
  return { startSec: Math.max(0, w.start_ms - padBeforeMs) / 1000, endSec: (w.end_ms + padAfterMs) / 1000 };
}
