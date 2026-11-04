import { test } from "node:test";
import assert from "node:assert/strict";
import { stepStates, isFinished, elapsedSeconds, longProgress, longStatusText, timeLeftText } from "./jobSteps.js";

const states = (job) => stepStates(job).map((s) => s.state);

test("queued job has everything pending except first as current", () => {
  assert.deepEqual(states({ status: "queued", step: "parse" }), ["current", "pending", "pending", "pending", "pending"]);
});
test("running align marks earlier steps done", () => {
  assert.deepEqual(states({ status: "running", step: "align" }), ["done", "done", "current", "pending", "pending"]);
});
test("done marks all done", () => {
  assert.deepEqual(states({ status: "done", step: "done" }), ["done", "done", "done", "done", "done"]);
});
test("failed marks the failing step", () => {
  assert.deepEqual(states({ status: "failed", step: "synthesize" }), ["done", "failed", "pending", "pending", "pending"]);
});
test("no job is all pending", () => assert.deepEqual(states(null), ["pending", "pending", "pending", "pending", "pending"]));
test("the translation is the last step, so a passage is never shown as ready before it", () => {
  assert.deepEqual(states({ status: "running", step: "translate" }), ["done", "done", "done", "done", "current"]);
});
test("isFinished", () => {
  assert.equal(isFinished({ status: "done" }), true);
  assert.equal(isFinished({ status: "running" }), false);
  assert.equal(isFinished(null), false);
});
test("elapsedSeconds", () => {
  assert.equal(elapsedSeconds("2026-01-01T00:00:00Z", "2026-01-01T00:00:07Z"), 7);
  assert.equal(elapsedSeconds("2026-01-01T00:00:00Z", null, Date.parse("2026-01-01T00:00:03Z")), 3);
  assert.equal(elapsedSeconds("bad", null), null);
});

import { friendlyJobError } from "./jobSteps.js";

test("a failed job shows a friendly message and never internal details", () => {
  const generic = "We could not finish creating the audio. Please try again in a moment.";
  assert.equal(friendlyJobError(null), generic);
  assert.equal(friendlyJobError(""), generic);
  for (const leak of [
    "Could not start the voice engine (ENOENT).",
    "Traceback (most recent call last): File run_local.py, line 3",
    "GET /api/jobs/abc failed",
    "https://example.amazonaws.com/x timed out",
    "Lambda timed out after 900 seconds",
    "Error at Object.run (/var/task/index.js:10:5)",
    "The server returned HTTP 500",
    "exit code 1, stderr: boom",
  ]) assert.equal(friendlyJobError(leak), generic, leak);
  assert.equal(friendlyJobError("Text must be at least 20 characters."), "Text must be at least 20 characters.");
  assert.equal(friendlyJobError("x".repeat(300)), generic);
});

test("a long text shows progress and the time left from the stretches already finished, and never the word part", () => {
  const job = (extra) => ({ status: "running", startedAt: "2026-11-04T10:00:00Z", finishedAt: null, chunksTotal: 5, chunksDone: 0, ...extra });
  const at = (s) => Date.parse("2026-11-04T10:00:00Z") + s * 1000;
  assert.equal(longProgress({ status: "running", startedAt: "2026-11-04T10:00:00Z" }, at(60)), null);  // an ordinary job has no chunks
  assert.deepEqual(longProgress(job(), at(30)), { done: 0, total: 5, percent: 0, remainingSeconds: null });  // nothing finished yet: no estimate
  assert.deepEqual(longProgress(job({ chunksDone: 2 }), at(240)), { done: 2, total: 5, percent: 40, remainingSeconds: 360 });  // 120 s per stretch, 3 left (no finish time known: elapsed / done)
  const known = job({ chunksDone: 2, chunkAt: "2026-11-04T10:04:00Z" });  // the second stretch finished at 240 s: 120 s per stretch
  assert.equal(longProgress(known, at(240)).remainingSeconds, 360);
  assert.equal(longProgress(known, at(300)).remainingSeconds, 300, "while the next stretch runs, the time left counts DOWN, it never grows");
  assert.equal(longProgress(known, at(1000)).remainingSeconds, 5, "and never goes below a few seconds while it is still working");
  assert.deepEqual(longProgress(job({ chunksDone: 5, status: "done", finishedAt: "2026-11-04T10:09:00Z" }), at(600)), { done: 5, total: 5, percent: 100, remainingSeconds: 0 });
  assert.equal(longProgress(job({ chunksDone: 5 }), at(600)).percent, 99, "100% only when the job is really done (the stretches are still being joined)");
  assert.equal(timeLeftText(null), "");
  assert.equal(timeLeftText(20), "less than a minute left");
  assert.equal(timeLeftText(360), "about 6 minutes left");
  assert.equal(timeLeftText(60), "about 1 minute left");
});

test("a long text shows one status line instead of steps that would restart for every stretch", () => {
  const job = (extra) => ({ status: "running", startedAt: "2026-11-04T10:00:00Z", chunksTotal: 3, chunksDone: 1, ...extra });
  assert.equal(longStatusText({ status: "running" }), "");
  assert.equal(longStatusText(job()), "Creating the narration and its translation...");
  assert.equal(longStatusText(job({ chunksDone: 3 })), "Putting everything together into one passage...");
  assert.equal(longStatusText(job({ chunksDone: 3, status: "done" })), "Everything is ready.");
  assert.equal(/part/i.test([job(), job({ chunksDone: 3 })].map(longStatusText).join(" ")), false);
});
