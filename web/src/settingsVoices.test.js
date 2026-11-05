import { test } from "node:test";
import assert from "node:assert/strict";
import { POLLY_QUALITY_OPTIONS, TTS_ENGINE_OPTIONS, formForEngine, isDirty, sampleFile, settingsPayload, voiceGroups, voicesForEngine } from "./settings.js";

const VOICES = [
  { id: "af_heart", label: "Heart (US female)", lang: "en", engine: "kokoro", recommended: true },
  { id: "ef_dora", label: "Dora (Spanish female)", lang: "es", engine: "kokoro", recommended: true },
  { id: "Ruth", label: "Ruth (US female)", lang: "en", engine: "polly", engines: ["neural", "generative"], recommended: false },
  { id: "Joanna", label: "Joanna (US female)", lang: "en", engine: "polly", engines: ["neural", "generative"], recommended: true },
  { id: "Lupe", label: "Lupe (US Spanish female)", lang: "es", engine: "polly", engines: ["neural"], recommended: false },
];
const DEFAULTS = { kokoro: { voice: "af_heart", voiceEs: "ef_dora" }, polly: { voice: "Joanna", voiceEs: "Lupe" } };

test("with Amazon Polly the menus list Polly voices; with the built-in voices they list the open-source ones", () => {
  assert.deepEqual(voicesForEngine(VOICES, "polly", "en").map((v) => v.id), ["Ruth", "Joanna"]);
  assert.deepEqual(voicesForEngine(VOICES, "polly", "es").map((v) => v.id), ["Lupe"]);
  assert.deepEqual(voicesForEngine(VOICES, "kokoro", "en").map((v) => v.id), ["af_heart"]);
  assert.deepEqual(voicesForEngine(VOICES, "kokoro", "es").map((v) => v.id), ["ef_dora"]);
  assert.deepEqual(voicesForEngine(undefined, "polly", "en"), []);
});

test("recommended voices come first and the rest sit under More voices", () => {
  const groups = voiceGroups(voicesForEngine(VOICES, "polly", "en"), "polly");
  assert.deepEqual(groups.map((g) => [g.label, g.voices.map((v) => v.id)]), [["Recommended voices", ["Joanna"]], ["More voices", ["Ruth"]]]);
});

test("when no Polly voice is recommended yet, there is one plain list and no claim of quality", () => {
  const groups = voiceGroups(voicesForEngine(VOICES, "polly", "es"), "polly");
  assert.deepEqual(groups.map((g) => [g.label, g.voices.map((v) => v.id)]), [["Voices", ["Lupe"]]]);
  assert.deepEqual(voiceGroups([], "polly"), []);
});

test("the built-in voices keep their listening-test heading", () => {
  const groups = voiceGroups(voicesForEngine(VOICES, "kokoro", "en"), "kokoro");
  assert.equal(groups[0].label, "Recommended (passed our listening test)");
});

test("switching the engine replaces voices the new engine does not offer with that engine's defaults", () => {
  const form = { voice: "af_heart", voiceEs: "ef_dora", speed: 1, mp3Kbps: 48, ttsEngine: "kokoro" };
  const next = formForEngine(form, "polly", VOICES, DEFAULTS);
  assert.deepEqual([next.ttsEngine, next.voice, next.voiceEs], ["polly", "Joanna", "Lupe"]);
  assert.equal(form.ttsEngine, "kokoro", "the form is not mutated");
  const keep = formForEngine({ ...form, ttsEngine: "polly", voice: "Ruth", voiceEs: "Lupe" }, "polly", VOICES, DEFAULTS);
  assert.deepEqual([keep.voice, keep.voiceEs], ["Ruth", "Lupe"]);
  const back = formForEngine({ ...form, ttsEngine: "polly", voice: "Ruth", voiceEs: "Lupe" }, "kokoro", VOICES, DEFAULTS);
  assert.deepEqual([back.voice, back.voiceEs], ["af_heart", "ef_dora"]);
});

test("without defaults from the server the first listed voice is used", () => {
  const next = formForEngine({ voice: "af_heart", voiceEs: "ef_dora", ttsEngine: "kokoro" }, "polly", VOICES, undefined);
  assert.deepEqual([next.voice, next.voiceEs], ["Ruth", "Lupe"]);
});

test("a Polly voice id is sent as voice and voiceEs, with the voice quality when chosen", () => {
  assert.deepEqual(settingsPayload({ voice: "Ruth", voiceEs: "Lupe", speed: 1, mp3Kbps: 48, ttsEngine: "polly", pollyEngine: "generative" }), {
    voice: "Ruth", voiceEs: "Lupe", speed: 1, mp3Kbps: 48, ttsEngine: "polly", pollyEngine: "generative",
  });
  assert.equal("pollyEngine" in settingsPayload({ voice: "a", speed: 1, mp3Kbps: 48 }), false);
});

test("picking another Polly voice or another quality marks the form dirty", () => {
  const saved = { voice: "Joanna", voiceEs: "Lupe", speed: 0.95, mp3Kbps: 48, ttsEngine: "polly", pollyEngine: "neural" };
  assert.equal(isDirty(saved, { ...saved }), false);
  assert.equal(isDirty(saved, { ...saved, voice: "Ruth" }), true);
  assert.equal(isDirty(saved, { ...saved, pollyEngine: "generative" }), true);
  assert.equal(isDirty({ ...saved, pollyEngine: undefined }, { ...saved, pollyEngine: "neural" }), false, "no saved quality means neural");
});

test("Polly samples live in polly-<VoiceId>.mp3 and the others keep their own file name", () => {
  assert.equal(sampleFile("Ruth", "polly"), "polly-Ruth");
  assert.equal(sampleFile("af_heart", "kokoro"), "af_heart");
  assert.equal(sampleFile("", "polly"), "");
});

test("teachers see only 'Built-in voices' and 'Amazon Polly', with plain voice-quality wording", () => {
  assert.deepEqual(TTS_ENGINE_OPTIONS.map((e) => e.label), ["Built-in voices", "Amazon Polly"]);
  assert.deepEqual(POLLY_QUALITY_OPTIONS.map((o) => o.label), ["Natural (neural)", "Most natural (generative)"]);
  const text = JSON.stringify([TTS_ENGINE_OPTIONS, POLLY_QUALITY_OPTIONS]);
  assert.doesNotMatch(text, /Kokoro|Phonon|Lambda|Whisper/);
  assert.doesNotMatch(TTS_ENGINE_OPTIONS[1].hint, /do not apply|Joanna for English/);
});
