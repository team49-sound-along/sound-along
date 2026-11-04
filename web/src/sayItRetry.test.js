import { test } from "node:test";
import assert from "node:assert/strict";
import { MAX_TRIES, initial, step, judge, listensNow, finished } from "./sayItRetry.js";

const run = (events, from = initial()) => events.reduce((s, e) => step(s, e), from);

test("starts idle", () => {
  assert.equal(initial().phase, "idle");
  assert.equal(MAX_TRIES, 2);
});

test("start plays the word slowly first when slow audio exists", () => {
  assert.equal(step(initial(), { type: "start", canSlow: true }).phase, "slow");
});

test("start goes straight to listening when there is no slow audio", () => {
  assert.equal(step(initial(), { type: "start", canSlow: false }).phase, "listening");
});

test("slow audio that could not play still leads to listening", () => {
  assert.equal(run([{ type: "start", canSlow: true }, { type: "slowEnded", ok: false }]).phase, "listening");
  assert.equal(run([{ type: "start", canSlow: true }, { type: "slowEnded", ok: true }]).phase, "listening");
});

test("success path: the word is heard", () => {
  const s = run([{ type: "start", canSlow: true }, { type: "slowEnded", ok: true }, { type: "heard" }]);
  assert.equal(s.phase, "success");
  assert.equal(s.tries, 1);
  assert.ok(finished(s));
});

test("retry path: one miss offers one more try, then a heard word is a success", () => {
  const miss = run([{ type: "start", canSlow: true }, { type: "slowEnded", ok: true }, { type: "missed" }]);
  assert.equal(miss.phase, "retry");
  assert.equal(miss.tries, 1);
  assert.equal(finished(miss), false);
  const again = run([{ type: "tryAgain", canSlow: true }, { type: "slowEnded", ok: true }, { type: "heard" }], miss);
  assert.equal(again.phase, "success");
  assert.equal(again.tries, 2);
});

test("after the second miss the learner is invited to carry on, never stuck", () => {
  const s = run([{ type: "start", canSlow: false }, { type: "missed" }, { type: "tryAgain", canSlow: false }, { type: "missed" }]);
  assert.equal(s.phase, "moveOn");
  assert.ok(finished(s));
  assert.equal(step(s, { type: "tryAgain", canSlow: false }).phase, "moveOn"); // no third try
});

test("a microphone problem ends the guided try without blame", () => {
  const s = run([{ type: "start", canSlow: false }, { type: "failed", message: "blocked" }]);
  assert.equal(s.phase, "unavailable");
  assert.equal(s.message, "blocked");
  assert.ok(finished(s));
});

test("skip and reset return to idle, and the old state is not changed", () => {
  const before = run([{ type: "start", canSlow: true }]);
  const frozen = JSON.stringify(before);
  assert.equal(step(before, { type: "stop" }).phase, "idle");
  assert.equal(step(before, { type: "reset" }).tries, 0);
  assert.equal(JSON.stringify(before), frozen);
});

test("events that do not fit the phase are ignored", () => {
  assert.equal(step(initial(), { type: "heard" }).phase, "idle");
  assert.equal(step(initial(), { type: "slowEnded", ok: true }).phase, "idle");
  assert.equal(step(initial(), { type: "missed" }).phase, "idle");
  assert.equal(step(initial(), { type: "nonsense" }).phase, "idle");
  assert.equal(step(initial(), null).phase, "idle");
  assert.equal(step(undefined, { type: "start" }).phase, "listening");
});

test("the microphone listens only in the listening phase", () => {
  assert.equal(listensNow(initial()), false);
  assert.equal(listensNow(step(initial(), { type: "start", canSlow: true })), false); // the audio would be heard otherwise
  assert.equal(listensNow(step(initial(), { type: "start", canSlow: false })), true);
});

test("judge: the right word, close spellings and filler words are a match", () => {
  assert.equal(judge("island", "island", "en", true), "match");
  assert.equal(judge("um island", "island", "en", true), "match");
  assert.equal(judge("Island!", "island", "en", false), "match");
  assert.equal(judge("the word is island", "island", "en", true), "match");
});

test("judge: another word is a miss only when the result is final", () => {
  assert.equal(judge("window", "island", "en", true), "miss");
  assert.equal(judge("banana", "island", "en", true), "miss");
  assert.equal(judge("banana", "island", "en", false), "pending");
  assert.equal(judge("", "island", "en", true), "miss");
});

test("judge: Spanish accents are forgiven, the tilde on n is not", () => {
  assert.equal(judge("construccion", "construcción", "es", true), "match");
  assert.equal(judge("ano", "año", "es", true), "miss");
});

test("judge: odd words and input never throw", () => {
  assert.equal(judge("hello", "", "en", true), "miss");
  assert.equal(judge(null, "island", "en", true), "miss");
  assert.equal(judge("hello", "...", "en", true), "miss");
  assert.equal(judge("2", "2", "en", true), "match");
});
