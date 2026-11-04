import { test } from "node:test";
import assert from "node:assert/strict";
import { stepStates, isFinished, elapsedSeconds } from "./jobSteps.js";

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
