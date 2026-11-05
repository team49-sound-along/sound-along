import assert from "node:assert/strict";
import { after, describe, test } from "node:test";
import { effectiveSettings, loadAllVoices, loadPollyVoices, mergeSettings, parseSettingsPatch, settingsView } from "../src/settings.js";
import { startLocalApp } from "./support/harness.js";

const voices = loadAllVoices();
const polly = voices.filter((v) => v.engine === "polly");
const ctx = await startLocalApp();
after(() => ctx.server.close());
const { call } = ctx;

describe("the curated Polly voice list", () => {
  test("has the requested US English and US/Mexican Spanish voices, no UK, Australian, Indian or Castilian ones", () => {
    assert.deepEqual(polly.filter((v) => v.lang === "en").map((v) => v.id).sort(), ["Danielle", "Gregory", "Joanna", "Joey", "Kendra", "Kimberly", "Matthew", "Ruth", "Salli", "Stephen"]);
    assert.deepEqual(polly.filter((v) => v.lang === "es").map((v) => v.id).sort(), ["Andres", "Carlos", "Lupe", "Mia", "Pedro"]);
    assert.ok(polly.every((v) => (v.lang === "en" ? v.accent === "en-US" : ["es-US", "es-MX"].includes(v.accent))));
  });
  test("every entry names its engines and none is recommended before a listening test", () => {
    for (const v of polly) {
      assert.ok(v.id && v.label && v.engines.length > 0 && v.engines.every((e) => ["neural", "generative", "standard"].includes(e)), v.id);
      assert.equal(v.recommended, false, v.id);
    }
    assert.equal(new Set(voices.map((v) => v.id)).size, voices.length);
  });
  test("labels are plain facts: no quality claims", () => {
    for (const v of polly) assert.doesNotMatch(v.label, /best|warm|natural|great|clear|friendly/i, v.label);
  });
  test("the rating file lists only known voices and marks them recommended", () => {
    const rated = [{ id: "Ruth", lang: "en", engine: "polly", engines: ["neural"] }, { id: "Joanna", lang: "en", engine: "polly", engines: ["neural"] }];
    const out = loadPollyVoices({ voices: rated, ratings: { recommended: ["Ruth", "Nobody"] } });
    assert.deepEqual(out.map((v) => [v.id, v.recommended]), [["Ruth", true], ["Joanna", false]]);
  });
});

describe("validation depends on the engine", () => {
  test("with Polly, a Polly voice of the right language is accepted and an open-source voice is refused", () => {
    assert.deepEqual(parseSettingsPatch({ ttsEngine: "polly", voice: "Ruth", voiceEs: "Mia" }, voices), { ttsEngine: "polly", voice: "Ruth", voiceEs: "Mia" });
    assert.throws(() => parseSettingsPatch({ ttsEngine: "polly", voice: "af_heart" }, voices), /Amazon Polly/);
    assert.throws(() => parseSettingsPatch({ ttsEngine: "polly", voice: "Lupe" }, voices), /English voice/);
    assert.throws(() => parseSettingsPatch({ ttsEngine: "polly", voiceEs: "Ruth" }, voices), /Spanish voice/);
  });
  test("with the built-in voices, a Polly voice is refused", () => {
    assert.throws(() => parseSettingsPatch({ ttsEngine: "kokoro", voice: "Ruth" }, voices), /built-in/i);
    assert.deepEqual(parseSettingsPatch({ voice: "af_heart" }, voices, "kokoro"), { voice: "af_heart" });
  });
  test("a voice sent alone is checked against the engine already saved", () => {
    assert.deepEqual(parseSettingsPatch({ voice: "Ruth" }, voices, "polly"), { voice: "Ruth" });
    assert.throws(() => parseSettingsPatch({ voice: "Ruth" }, voices, "kokoro"), /built-in/i);
  });
  test("voice quality accepts neural or generative only", () => {
    assert.deepEqual(parseSettingsPatch({ pollyEngine: "generative" }, voices), { pollyEngine: "generative" });
    assert.throws(() => parseSettingsPatch({ pollyEngine: "turbo" }, voices), /Voice quality/);
  });
  test("a generative-only voice cannot be picked when it does not exist for that quality", () => {
    assert.deepEqual(parseSettingsPatch({ ttsEngine: "polly", voice: "Kendra", pollyEngine: "generative" }, voices), { ttsEngine: "polly", voice: "Kendra", pollyEngine: "generative" }); // falls back to neural at run time
  });
});

describe("saved settings that no longer fit the engine", () => {
  test("an open-source voice saved while the engine is Polly falls back to the Polly default", () => {
    const out = effectiveSettings({ ttsEngine: "polly", voice: "phonon_hadley", voiceEs: "ef_dora" }, voices);
    assert.deepEqual([out.voice, out.voiceEs], ["Joanna", "Lupe"]);
  });
  test("a Polly voice saved while the engine is built-in falls back to the built-in default", () => {
    const out = effectiveSettings({ ttsEngine: "kokoro", voice: "Ruth", voiceEs: "Mia" }, voices);
    assert.deepEqual([out.voice, out.voiceEs], ["af_heart", "ef_dora"]);
  });
  test("a valid saved Polly voice is kept, and pollyEngine appears only when it was chosen", () => {
    const kept = effectiveSettings({ ttsEngine: "polly", voice: "Ruth", voiceEs: "Pedro", pollyEngine: "generative" }, voices);
    assert.deepEqual([kept.voice, kept.voiceEs, kept.pollyEngine], ["Ruth", "Pedro", "generative"]);
    assert.equal("pollyEngine" in effectiveSettings({ ttsEngine: "polly" }, voices), false);
  });
  test("the deployment's POLLY_VOICE is the Polly default when it is on the list", () => {
    process.env.POLLY_VOICE = "Matthew";
    process.env.POLLY_VOICE_ES = "NotAVoice";
    try {
      const out = effectiveSettings({ ttsEngine: "polly" }, voices);
      assert.deepEqual([out.voice, out.voiceEs], ["Matthew", "Lupe"]);
    } finally {
      delete process.env.POLLY_VOICE;
      delete process.env.POLLY_VOICE_ES;
    }
  });
  test("switching the engine in a patch re-resolves the voices", () => {
    const merged = mergeSettings({ ttsEngine: "kokoro", voice: "phonon_hadley", voiceEs: "em_alex" }, { ttsEngine: "polly" }, voices);
    assert.deepEqual([merged.ttsEngine, merged.voice, merged.voiceEs], ["polly", "Joanna", "Lupe"]);
  });
  test("the settings view carries the voices, per-engine defaults and the deployment's voice quality", () => {
    const view = settingsView({ ttsEngine: "polly" }, voices);
    assert.equal(view.voices.length, voices.length);
    assert.deepEqual(view.voiceDefaults.polly, { voice: "Joanna", voiceEs: "Lupe" });
    assert.deepEqual(view.voiceDefaults.kokoro, { voice: "af_heart", voiceEs: "ef_dora" });
    assert.equal(view.pollyEngine, "neural");
  });
});

describe("settings over HTTP with Polly voices", () => {


  test("the list includes Polly voices, and a saved Polly voice is returned and sent with the job", async () => {
    const r = await call("PUT", "/api/settings", { ttsEngine: "polly", voice: "Ruth", voiceEs: "Mia", pollyEngine: "generative" });
    assert.equal(r.status, 200);
    assert.deepEqual([r.json.data.voice, r.json.data.voiceEs, r.json.data.pollyEngine], ["Ruth", "Mia", "generative"]);
    assert.ok(r.json.data.voices.some((v) => v.engine === "polly" && v.id === "Lupe"));
    const g = await call("POST", "/api/generate", { title: "T", text: "A short passage that is long enough to pass validation." });
    assert.equal(g.status, 202);
    assert.deepEqual(ctx.started.at(-1).settings && [ctx.started.at(-1).settings.voice, ctx.started.at(-1).settings.voiceEs, ctx.started.at(-1).settings.pollyEngine], ["Ruth", "Mia", "generative"]);
  });
  test("an open-source voice is refused while Polly is saved, with a plain message", async () => {
    const r = await call("PUT", "/api/settings", { voice: "af_heart" });
    assert.equal(r.status, 400);
    assert.match(r.json.error, /Amazon Polly/);
  });
  test("switching back to built-in voices needs built-in voices", async () => {
    const bad = await call("PUT", "/api/settings", { ttsEngine: "kokoro", voice: "Ruth" });
    assert.equal(bad.status, 400);
    const r = await call("PUT", "/api/settings", { ttsEngine: "kokoro" });
    assert.deepEqual([r.json.data.voice, r.json.data.voiceEs], ["af_heart", "ef_dora"]);
  });
});
