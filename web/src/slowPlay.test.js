import { test } from "node:test";
import assert from "node:assert/strict";
import { SLOW_RATE, slowWindow, createSlowPlayer } from "./slowPlay.js";

const words = [
  { i: 0, text: "I", start_ms: 0, end_ms: 300, aligned: true },
  { i: 1, text: "island", start_ms: 1000, end_ms: 1600, aligned: true },
  { i: 2, text: "guess", start_ms: 2000, end_ms: 2400, aligned: false },
];

test("slow window is the word's slice at the slow rate", () => {
  const w = slowWindow(words, 1);
  assert.equal(w.rate, SLOW_RATE);
  assert.equal(SLOW_RATE, 0.6);
  assert.ok(Math.abs(w.startSec - 0.96) < 1e-9 && Math.abs(w.endSec - 1.68) < 1e-9);
  assert.ok(Math.abs(w.wallSec - 0.72 / 0.6) < 1e-9); // real time it takes at the slow rate
});

test("a word at the very start never starts before zero", () => {
  assert.equal(slowWindow(words, 0).startSec, 0);
});

test("no window when timing is only estimated, missing, or out of range", () => {
  assert.equal(slowWindow(words, 2), null);
  assert.equal(slowWindow(words, 9), null);
  assert.equal(slowWindow(words, -1), null);
  assert.equal(slowWindow([], 0), null);
  assert.equal(slowWindow(null, 0), null);
  assert.equal(slowWindow([{ i: 0, text: "x" }], 0), null);
});

test("the rate is kept between half speed and normal speed", () => {
  assert.equal(slowWindow(words, 1, { rate: 0.1 }).rate, 0.5);
  assert.equal(slowWindow(words, 1, { rate: 3 }).rate, 1);
  assert.equal(slowWindow(words, 1, { rate: "x" }).rate, SLOW_RATE);
});

function fakeAudio({ rejects = false } = {}) {
  const log = [];
  const el = {
    playbackRate: 1.25, preservesPitch: false, currentTime: 0, paused: true,
    play() { log.push("play"); this.paused = false; return rejects ? Promise.reject(new Error("blocked")) : Promise.resolve(); },
    pause() { log.push("pause"); this.paused = true; },
  };
  return { el, log };
}
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

test("plays the slice slowly with pitch kept, stops at the end, and restores the speed", async () => {
  const { el, log } = fakeAudio();
  const player = createSlowPlayer({ pollMs: 5 });
  const ends = [];
  player.play(el, { startSec: 1, endSec: 1.2, rate: 0.6, wallSec: 0.3 }, (ok) => ends.push(ok));
  await wait(10);
  assert.equal(el.playbackRate, 0.6);
  assert.equal(el.preservesPitch, true);
  assert.equal(el.currentTime, 1);
  el.currentTime = 1.25;
  await wait(20);
  assert.deepEqual(ends, [true]);
  assert.equal(el.playbackRate, 1.25);
  assert.equal(el.paused, true);
  assert.deepEqual(log, ["play", "pause"]);
});

test("gives up after the expected time if the audio never reaches the end", async () => {
  const { el } = fakeAudio();
  const player = createSlowPlayer({ pollMs: 5, graceMs: 20 });
  const ends = [];
  player.play(el, { startSec: 1, endSec: 1.2, rate: 0.6, wallSec: 0.05 }, (ok) => ends.push(ok));
  await wait(120);
  assert.deepEqual(ends, [true]);
  assert.equal(el.playbackRate, 1.25);
});

test("a blocked or failed play reports false and restores the speed", async () => {
  const { el } = fakeAudio({ rejects: true });
  const player = createSlowPlayer({ pollMs: 5 });
  const ends = [];
  player.play(el, { startSec: 1, endSec: 1.2, rate: 0.6, wallSec: 0.3 }, (ok) => ends.push(ok));
  await wait(30);
  assert.deepEqual(ends, [false]);
  assert.equal(el.playbackRate, 1.25);
});

test("starting again, or cancel, ends the earlier play once", async () => {
  const { el } = fakeAudio();
  const player = createSlowPlayer({ pollMs: 5 });
  const first = [];
  const second = [];
  player.play(el, { startSec: 1, endSec: 9, rate: 0.6, wallSec: 5 }, (ok) => first.push(ok));
  player.play(el, { startSec: 2, endSec: 2.1, rate: 0.6, wallSec: 0.1 }, (ok) => second.push(ok));
  assert.deepEqual(first, [false]);
  assert.equal(el.playbackRate, 0.6); // the second play keeps the slow rate, and remembers the learner's real speed
  player.cancel();
  assert.deepEqual(second, [false]);
  assert.equal(el.playbackRate, 1.25);
  player.cancel(); // harmless
});

test("no audio element means false, not a crash", () => {
  const ends = [];
  createSlowPlayer().play(null, { startSec: 0, endSec: 1, rate: 0.6, wallSec: 1 }, (ok) => ends.push(ok));
  createSlowPlayer().play({}, null, (ok) => ends.push(ok));
  assert.deepEqual(ends, [false, false]);
});
