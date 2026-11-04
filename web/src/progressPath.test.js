import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { pathPoints, pathSummary, progressLabel } from "./progressPath.js";

describe("progressLabel", () => {
  test("one read is just a start", () => {
    assert.deepEqual(progressLabel([40]), { label: "Just getting started", tone: "new" });
    assert.deepEqual(progressLabel([]), { label: "Just getting started", tone: "new" });
  });
  test("reading more each time", () => {
    assert.equal(progressLabel([30, 45, 62, 80]).label, "Reading more each time");
    assert.equal(progressLabel([20, 40]).tone, "up");
  });
  test("steady when the amount stays about the same and is mostly read", () => {
    assert.deepEqual(progressLabel([70, 72, 69, 71]), { label: "Steady", tone: "steady" });
  });
  test("needs support when reading less, or reading under half without improving", () => {
    assert.deepEqual(progressLabel([60, 40, 35, 25]), { label: "Needs support", tone: "help" });
    assert.equal(progressLabel([20, 22, 21]).label, "Needs support");
  });
  test("improving from a low start still reads as progress", () => {
    assert.equal(progressLabel([10, 20, 35]).label, "Reading more each time");
  });
});

describe("pathPoints", () => {
  test("dots are spread left to right; a higher share sits higher", () => {
    const pts = pathPoints([0, 50, 100], { width: 100, height: 40, pad: 10 });
    assert.deepEqual(pts.map((p) => p.x), [10, 50, 90]);
    assert.deepEqual(pts.map((p) => p.y), [30, 20, 10]);
  });
  test("a single read sits in the middle", () => {
    assert.equal(pathPoints([50], { width: 100, height: 40, pad: 10 })[0].x, 50);
  });
});

describe("pathSummary", () => {
  test("a plain text alternative", () => {
    assert.equal(pathSummary([30, 45, 62]), "Read 30%, 45%, 62% of the passage over 3 reads");
    assert.equal(pathSummary([30]), "Read 30% of the passage in 1 read");
    assert.equal(pathSummary([]), "No reads yet");
  });
});
