import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { progressLabel } from "./progressPath.js";

describe("progressLabel (one word per reader)", () => {
  test("one read is new", () => {
    assert.deepEqual(progressLabel([40]), { label: "New", tone: "new" });
    assert.deepEqual(progressLabel([]), { label: "New", tone: "new" });
  });
  test("improving when more of the passage is read each time", () => {
    assert.equal(progressLabel([30, 45, 62, 80]).label, "Improving");
    assert.equal(progressLabel([20, 40]).tone, "up");
    assert.equal(progressLabel([10, 20, 35]).label, "Improving");
  });
  test("steady when the amount stays about the same and is mostly read", () => {
    assert.deepEqual(progressLabel([70, 72, 69, 71]), { label: "Steady", tone: "steady" });
  });
  test("support when reading less, or reading under half without improving", () => {
    assert.deepEqual(progressLabel([60, 40, 35, 25]), { label: "Support", tone: "help" });
    assert.equal(progressLabel([20, 22, 21]).label, "Support");
  });
});
