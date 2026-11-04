import { test } from "node:test";
import assert from "node:assert/strict";
import { isDirty, mbPerMinute, settingsPayload, snapSpeed } from "./settings.js";

test("size per minute", () => {
  assert.equal(mbPerMinute(48), 0.36);
  assert.equal(mbPerMinute(128), 0.96);
});
test("snapSpeed clamps and snaps", () => {
  assert.equal(snapSpeed(0.951), 0.95);
  assert.equal(snapSpeed(0.2), 0.7);
  assert.equal(snapSpeed(9), 1.2);
});
test("payload coerces types", () => {
  assert.deepEqual(settingsPayload({ voice: "af_heart", speed: "0.95", mp3Kbps: "48" }), { voice: "af_heart", speed: 0.95, mp3Kbps: 48 });
});
test("dirty detection", () => {
  const s = { voice: "a", speed: 0.95, mp3Kbps: 48 };
  assert.equal(isDirty(s, { voice: "a", speed: 0.95, mp3Kbps: "48" }), false);
  assert.equal(isDirty(s, { voice: "b", speed: 0.95, mp3Kbps: 48 }), true);
});

test("Spanish voice is sent only when chosen and counts for dirty", () => {
  assert.deepEqual(settingsPayload({ voice: "a", voiceEs: "ef_dora", speed: 1, mp3Kbps: 48 }), { voice: "a", voiceEs: "ef_dora", speed: 1, mp3Kbps: 48 });
  const s = { voice: "a", voiceEs: "ef_dora", speed: 1, mp3Kbps: 48 };
  assert.equal(isDirty(s, { ...s, voiceEs: "em_alex" }), true);
  assert.equal(isDirty(s, { ...s }), false);
});

test("the narration engine is sent when chosen and counts for dirty", () => {
  const s = { voice: "a", speed: 1, mp3Kbps: 48, ttsEngine: "kokoro" };
  assert.deepEqual(settingsPayload({ ...s, ttsEngine: "polly" }), { voice: "a", speed: 1, mp3Kbps: 48, ttsEngine: "polly" });
  assert.equal(isDirty(s, { ...s }), false);
  assert.equal(isDirty(s, { ...s, ttsEngine: "polly" }), true);
  assert.equal(isDirty({ voice: "a", speed: 1, mp3Kbps: 48 }, { ...s }), false, "an older API without ttsEngine means kokoro");
});
