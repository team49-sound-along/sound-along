import { test } from "node:test";
import assert from "node:assert/strict";
import { stepStates, isFinished, elapsedSeconds } from "./jobSteps.js";

const states = (job) => stepStates(job).map((s) => s.state);

test("queued job has everything pending except first as current", () => {
  assert.deepEqual(states({ status: "queued", step: "parse" }), ["current", "pending", "pending", "pending"]);
});
test("running align marks earlier steps done", () => {
  assert.deepEqual(states({ status: "running", step: "align" }), ["done", "done", "current", "pending"]);
});
test("done marks all done", () => {
  assert.deepEqual(states({ status: "done", step: "done" }), ["done", "done", "done", "done"]);
});
test("failed marks the failing step", () => {
  assert.deepEqual(states({ status: "failed", step: "synthesize" }), ["done", "failed", "pending", "pending"]);
});
test("no job is all pending", () => assert.deepEqual(states(null), ["pending", "pending", "pending", "pending"]));
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
