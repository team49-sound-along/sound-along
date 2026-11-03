import assert from "node:assert/strict";
import { after, describe, test } from "node:test";
import { mergeSettings, parseSettingsPatch, loadVoices } from "../src/settings.js";
import { startLocalApp } from "./support/harness.js";

const ctx = await startLocalApp();
after(() => ctx.server.close());
const { call } = ctx;

describe("settings", () => {
  test("GET returns defaults and the voice list when nothing is stored", async () => {
    const { json } = await call("GET", "/api/settings");
    assert.deepEqual([json.data.voice, json.data.speed, json.data.mp3Kbps], ["af_heart", 0.95, 48]);
    assert.equal(json.data.voices.length, 6);
    assert.ok(json.data.voices.every((v) => v.id && v.label));
  });

  test("PUT merges partial updates and persists them", async () => {
    const first = await call("PUT", "/api/settings", { speed: 1.1 });
    assert.equal(first.status, 200);
    assert.deepEqual([first.json.data.voice, first.json.data.speed, first.json.data.mp3Kbps], ["af_heart", 1.1, 48]);
    await call("PUT", "/api/settings", { voice: loadVoices()[0].id, mp3Kbps: 64 });
    const { json } = await call("GET", "/api/settings");
    assert.deepEqual([json.data.voice, json.data.speed, json.data.mp3Kbps], [loadVoices()[0].id, 1.1, 64]);
  });

  test("rejects bad values with readable messages", async () => {
    const cases = [
      [{ voice: "nope" }, /voice/i],
      [{ speed: 0.5 }, /speed/i],
      [{ speed: "fast" }, /speed/i],
      [{ speed: 1.3 }, /speed/i],
      [{ mp3Kbps: 20 }, /kbps/i],
      [{ mp3Kbps: 64.5 }, /kbps/i],
      [{ mp3Kbps: 129 }, /kbps/i],
      [{}, /at least one/i],
      [[], /JSON object/i],
    ];
    for (const [body, pattern] of cases) {
      const r = await call("PUT", "/api/settings", body);
      assert.equal(r.status, 400, JSON.stringify(body));
      assert.match(r.json.error, pattern);
    }
    assert.equal((await call("GET", "/api/settings")).json.data.mp3Kbps, 64, "invalid updates change nothing");
  });
});

describe("settings helpers", () => {
  test("mergeSettings never mutates its inputs and accepts boundary values", () => {
    const current = Object.freeze({ voice: "af_heart", speed: 0.95, mp3Kbps: 48 });
    const next = mergeSettings(current, { speed: 0.7 });
    assert.equal(next.speed, 0.7);
    assert.equal(current.speed, 0.95);
    assert.deepEqual(mergeSettings(null, {}), { voice: "af_heart", voiceEs: "ef_dora", speed: 0.95, mp3Kbps: 48 });
    const patch = parseSettingsPatch({ speed: 1.2, mp3Kbps: 24 }, loadVoices());
    assert.deepEqual(patch, { speed: 1.2, mp3Kbps: 24 });
  });
});
