import { test } from "node:test";
import assert from "node:assert/strict";
import { createRecognizer, describeError, getRecognitionCtor, recognitionLang, recognitionSupported } from "./speechRecognizer.js";

class FakeRecognition {
  static instances = [];
  constructor() {
    this.started = false;
    this.stopped = false;
    FakeRecognition.instances.push(this);
  }
  start() { this.started = true; this.onstart?.(); }
  stop() { this.stopped = true; setTimeout(() => this.onend?.(), 0); } // like the browser: the session ends a moment later
  say(items, resultIndex = 0) {
    const results = items.map(([transcript, isFinal]) => Object.assign([{ transcript }], { isFinal }));
    this.onresult?.({ resultIndex, results });
  }
}

const tick = () => new Promise((r) => setTimeout(r, 5));

function setup(language = "en") {
  FakeRecognition.instances = [];
  const results = [];
  const statuses = [];
  const errors = [];
  const timers = [];
  const rec = createRecognizer({
    language, Ctor: FakeRecognition, onResult: (r) => results.push(r), onStatus: (s) => statuses.push(s), onError: (e) => errors.push(e),
    setTimer: (fn) => timers.push(fn) && timers.length, clearTimer: () => {},
  });
  const last = () => FakeRecognition.instances.at(-1);
  const runTimers = () => timers.splice(0).forEach((fn) => fn());
  return { rec, results, statuses, errors, last, runTimers };
}

test("feature detection finds either constructor and tolerates none", () => {
  const A = function A() {};
  assert.equal(getRecognitionCtor({ SpeechRecognition: A }), A);
  assert.equal(getRecognitionCtor({ webkitSpeechRecognition: A }), A);
  assert.equal(recognitionSupported({}), false);
  assert.equal(recognitionSupported({ webkitSpeechRecognition: A }), true);
  assert.equal(recognitionSupported(undefined), false);
});

test("the recognition language follows the passage language", () => {
  assert.equal(recognitionLang("es"), "es-US");
  assert.equal(recognitionLang("en"), "en-US");
  assert.equal(recognitionLang(undefined), "en-US");
});

test("start configures continuous interim recognition in the passage language", () => {
  const { rec, last, statuses } = setup("es");
  assert.equal(rec.start(), true);
  assert.equal(last().continuous, true);
  assert.equal(last().interimResults, true);
  assert.equal(last().lang, "es-US");
  assert.deepEqual(statuses, ["starting", "listening"]);
});

test("results are passed on with ids that stay unique across sessions", () => {
  const { rec, results, last, runTimers } = setup();
  rec.start();
  last().say([["the dog", false]]);
  last().say([["the dog ran", true], ["to the", false]], 0);
  last().onend();
  runTimers();
  last().say([["barn", true]]);
  assert.deepEqual(results.map((r) => [r.id, r.isFinal]), [[10000, false], [10000, true], [10001, false], [10001, true], [20000, true]]);
});

test("a session that ends mid-sentence flushes its interim words as final, then restarts by itself", () => {
  const { rec, results, last, runTimers, statuses } = setup();
  rec.start();
  last().say([["the dog ran", false]]);
  last().onend();
  assert.deepEqual(results.at(-1), { id: 10000, transcript: "the dog ran", isFinal: true });
  assert.equal(statuses.at(-1), "restarting");
  runTimers();
  assert.equal(FakeRecognition.instances.length, 2);
  assert.equal(last().started, true);
});

test("stop ends listening and does not restart", async () => {
  const { rec, last, runTimers, statuses } = setup();
  rec.start();
  rec.stop();
  await tick();
  runTimers();
  assert.equal(FakeRecognition.instances.length, 1);
  assert.equal(statuses.at(-1), "idle");
  assert.equal(rec.isRunning(), false);
});

test("a blocked microphone stops with a friendly message and no restart", () => {
  const { rec, errors, last, runTimers } = setup();
  rec.start();
  last().onerror({ error: "not-allowed" });
  last().onend();
  runTimers();
  assert.equal(errors.length, 1);
  assert.equal(errors[0].fatal, true);
  assert.match(errors[0].message, /microphone is blocked/);
  assert.equal(FakeRecognition.instances.length, 1);
});

test("silence is not an error at first, but repeated silence stops with a hint", () => {
  const { rec, errors, last, runTimers } = setup();
  rec.start();
  for (let i = 0; i < 2; i += 1) {
    last().onerror({ error: "no-speech" });
    last().onend();
    runTimers();
  }
  assert.equal(errors.length, 0);
  last().onerror({ error: "no-speech" });
  last().onend();
  assert.equal(errors.length, 1);
  assert.match(errors[0].message, /could not hear anything/);
  assert.equal(rec.isRunning(), false);
});

test("speech resets the silence count", () => {
  const { rec, errors, last, runTimers } = setup();
  rec.start();
  for (let i = 0; i < 5; i += 1) {
    last().say([["hello", true]]);
    last().onerror({ error: "no-speech" });
    last().onend();
    runTimers();
  }
  assert.equal(errors.length, 0);
});

test("a network failure and a missing microphone have their own messages", () => {
  assert.match(describeError("network").message, /internet connection/);
  assert.match(describeError("audio-capture").message, /No microphone/);
  assert.equal(describeError("aborted").fatal, false);
  assert.equal(describeError("something-new").fatal, true);
  assert.match(describeError(undefined).message, /Listening stopped/);
});

test("an unsupported browser reports instead of throwing", () => {
  const errors = [];
  const rec = createRecognizer({ language: "en", Ctor: null, onResult: () => {}, onError: (e) => errors.push(e) });
  assert.equal(rec.start(), false);
  assert.equal(errors.length, 1);
});

test("a constructor or start() that throws is reported", () => {
  const errors = [];
  class Broken { start() { throw new Error("InvalidStateError"); } }
  const rec = createRecognizer({ language: "en", Ctor: Broken, onResult: () => {}, onError: (e) => errors.push(e) });
  rec.start();
  assert.equal(errors.length, 1);
  assert.equal(rec.isRunning(), false);
});

test("stop then immediate start: late results and a late end from the old session are ignored", async () => {
  const { rec, results, statuses, last, runTimers } = setup();
  rec.start();
  const old = last();
  const lateResult = old.onresult;
  const lateEnd = old.onend;
  old.say([["the dog", false]]);
  rec.stop();
  rec.start();
  const fresh = last();
  assert.notEqual(fresh, old);
  results.length = 0;
  lateResult({ resultIndex: 0, results: [Object.assign([{ transcript: "stale" }], { isFinal: true })] });
  lateEnd();
  await tick();
  runTimers();
  assert.equal(FakeRecognition.instances.length, 2, "no extra recognizer was started");
  fresh.say([["hello", false]]);
  fresh.say([["hello there", true]]);
  assert.deepEqual(results.map((r) => [r.id, r.transcript, r.isFinal]), [[20000, "hello", false], [20000, "hello there", true]]);
  assert.equal(rec.isRunning(), true);
  assert.notEqual(statuses.at(-1), "idle");
});

test("an old end never schedules a second restart or clears the new session", async () => {
  const { rec, last, runTimers } = setup();
  rec.start();
  const old = last();
  const lateEnd = old.onend;
  rec.stop();
  rec.start();
  lateEnd();
  await tick();
  runTimers();
  assert.equal(FakeRecognition.instances.length, 2);
  last().onend(); // the new session ends by itself: exactly one restart
  runTimers();
  assert.equal(FakeRecognition.instances.length, 3);
});

test("the final stop() really stops the new recognizer", async () => {
  const { rec, last, runTimers, statuses } = setup();
  rec.start();
  rec.stop();
  rec.start();
  const fresh = last();
  await tick();
  rec.stop();
  await tick();
  runTimers();
  assert.equal(fresh.stopped, true);
  assert.equal(FakeRecognition.instances.length, 2);
  assert.equal(statuses.at(-1), "idle");
  assert.equal(rec.isRunning(), false);
});

test("stopping mid-sentence keeps the words heard so far", () => {
  const { rec, results, last } = setup();
  rec.start();
  last().say([["the dog ran", false]]);
  rec.stop();
  assert.deepEqual(results.at(-1), { id: 10000, transcript: "the dog ran", isFinal: true });
});
