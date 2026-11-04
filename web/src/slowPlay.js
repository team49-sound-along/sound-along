// "Hear it slowly": the narration's own slice of one word, played at a slower speed with the pitch kept. No new audio is made, so it is
// only offered for words whose timing is trusted (the same rule as "Hear it", wordSlice in timing.js).
import { wordSlice } from "./timing.js";

export const SLOW_RATE = 0.5; // clearly slower than speech but still easy to follow (0.6 was too fast to catch, 0.4 played twice was too slow)
const MIN_RATE = 0.25;
const MAX_RATE = 1;

/** { startSec, endSec, rate, wallSec } for a word, or null when there is no trusted timing. wallSec is how long it takes at that rate. */
export function slowWindow(words, index, { rate = SLOW_RATE } = {}) {
  const slice = Array.isArray(words) ? wordSlice(words, index) : null;
  if (!slice) return null;
  const clamped = Number.isFinite(rate) ? Math.min(MAX_RATE, Math.max(MIN_RATE, rate)) : SLOW_RATE;
  return { ...slice, rate: clamped, wallSec: (slice.endSec - slice.startSec) / clamped };
}

/**
 * One slow play at a time. play(el, window, onEnd) calls onEnd(true) when the word has been played, or onEnd(false) when it could not
 * start or was replaced or cancelled. The audio element's speed is put back as it was. The clock is also a limit: if the audio stalls,
 * the play still ends shortly after the time the word should take.
 */
export function createSlowPlayer({ pollMs = 30, graceMs = 600 } = {}) {
  let active = null;

  function finish(ok) {
    const run = active;
    if (!run) return;
    active = null;
    clearInterval(run.poll);
    clearTimeout(run.limit);
    try {
      if (!run.el.paused) run.el.pause();
    } catch {
      // the element is gone
    }
    if (!run.keepRate) run.el.playbackRate = run.previousRate;
    run.onEnd?.(ok);
  }

  function play(el, win, onEnd) {
    if (!el || !win) {
      onEnd?.(false);
      return;
    }
    let previousRate = Number.isFinite(el.playbackRate) ? el.playbackRate : 1;
    if (active) {
      previousRate = active.previousRate; // the learner's own speed, not the slow one left by the earlier play
      active.keepRate = true;
      finish(false);
    }
    const run = { el, onEnd, previousRate, keepRate: false, poll: null, limit: null };
    active = run;
    try {
      el.playbackRate = win.rate;
      el.preservesPitch = true;
      el.mozPreservesPitch = true;
      el.webkitPreservesPitch = true;
      el.currentTime = win.startSec;
      Promise.resolve(el.play()).catch(() => {
        if (active === run) finish(false);
      });
    } catch {
      finish(false);
      return;
    }
    run.poll = setInterval(() => {
      if (el.currentTime >= win.endSec) finish(true);
    }, pollMs);
    run.limit = setTimeout(() => finish(true), win.wallSec * 1000 + graceMs);
  }

  return { play, cancel: () => finish(false) };
}
