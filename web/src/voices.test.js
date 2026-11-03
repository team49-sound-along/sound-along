import { test } from "node:test";
import assert from "node:assert/strict";
import { groupVariants, isHuman, readTarget, resumeIndex, voiceLabel } from "./voices.js";

const ai = { id: "a", engine: "kokoro", pairId: "h" };
const human = { id: "h", engine: "human", pairId: "a" };
const lone = { id: "x", engine: "kokoro", pairId: null };

test("grouping hides the human variant and records it on the AI passage", () => {
  const out = groupVariants([ai, human, lone]);
  assert.deepEqual(out.map((p) => p.id), ["a", "x"]);
  assert.equal(out[0].humanId, "h");
  assert.equal(out[1].humanId, undefined);
});

test("a human variant whose pair is missing stays visible", () => {
  assert.deepEqual(groupVariants([human]).map((p) => p.id), ["h"]);
});

test("grouping does not mutate its input", () => {
  const input = [ai, human];
  const snapshot = JSON.stringify(input);
  groupVariants(input);
  assert.equal(JSON.stringify(input), snapshot);
});

test("read target prefers the human narration", () => {
  assert.equal(readTarget({ id: "a", humanId: "h" }), "h");
  assert.equal(readTarget({ id: "x" }), "x");
});

test("labels and detection", () => {
  assert.equal(voiceLabel("human"), "Human narrator");
  assert.equal(voiceLabel("kokoro"), "Read-aloud voice");
  assert.equal(isHuman(human), true);
  assert.equal(isHuman(undefined), false);
});

test("resume index validates the query", () => {
  assert.equal(resumeIndex({ at: "12" }, 100), 12);
  assert.equal(resumeIndex({ at: "100" }, 100), null);
  assert.equal(resumeIndex({ at: "-1" }, 100), null);
  assert.equal(resumeIndex({ at: "abc" }, 100), null);
  assert.equal(resumeIndex({}, 100), null);
});
