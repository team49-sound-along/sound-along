import assert from "node:assert/strict";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, describe, test } from "node:test";
import { createDynamoCatalog } from "../src/aws/dynamoCatalog.js";
import { createDynamoStore } from "../src/aws/dynamoStore.js";
import { buildJobInput } from "../src/jobs/jobInput.js";
import { summarizePassage } from "../src/passageSummary.js";
import { loadVoices, mergeSettings, parseSettingsPatch } from "../src/settings.js";
import { seed } from "../scripts/seed.js";
import { TEXT, fakeClient, quiet, startLocalApp } from "./support/harness.js";

const ID = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98";

describe("voices.json", () => {
  const voices = loadVoices();
  test("only the four B- or better English voices and the three Spanish voices, every entry with a lang", () => {
    assert.deepEqual(voices.filter((v) => v.lang === "en").map((v) => v.id), ["af_heart", "af_bella", "af_nicole", "bf_emma"]);
    assert.ok(voices.every((v) => v.id && v.label && ["en", "es"].includes(v.lang)));
    assert.deepEqual(voices.filter((v) => v.lang === "es"), [
      { id: "ef_dora", label: "Dora (Spanish female, not graded)", lang: "es" },
      { id: "em_alex", label: "Alex (Spanish male, not graded)", lang: "es" },
      { id: "em_santa", label: "Santa (Spanish male, not graded)", lang: "es" },
    ]);
    assert.equal(new Set(voices.map((v) => v.id)).size, voices.length);
  });
});

describe("voiceEs settings", async () => {
  const ctx = await startLocalApp();
  after(() => ctx.close());
  const { call } = ctx;

  test("defaults, persists and is listed with lang in voices", async () => {
    const first = (await call("GET", "/api/settings")).json.data;
    assert.deepEqual([first.voice, first.voiceEs], ["af_heart", "ef_dora"]);
    assert.ok(first.voices.every((v) => v.lang));
    const put = await call("PUT", "/api/settings", { voiceEs: "em_alex" });
    assert.equal(put.json.data.voiceEs, "em_alex");
    assert.equal(put.json.data.voice, "af_heart");
    assert.equal((await call("GET", "/api/settings")).json.data.voiceEs, "em_alex");
  });

  test("voice must be English and voiceEs Spanish", async () => {
    const cases = [
      [{ voice: "ef_dora" }, /English voice/],
      [{ voiceEs: "af_heart" }, /Spanish voice/],
      [{ voiceEs: "nope" }, /Spanish voice/],
      [{ voiceEs: 3 }, /Spanish voice/],
    ];
    for (const [body, pattern] of cases) {
      const r = await call("PUT", "/api/settings", body);
      assert.equal(r.status, 400, JSON.stringify(body));
      assert.match(r.json.error, pattern);
    }
    assert.equal((await call("GET", "/api/settings")).json.data.voiceEs, "em_alex");
  });

  test("helpers: patch keeps only sent fields and merge never mutates", () => {
    assert.deepEqual(parseSettingsPatch({ voiceEs: "em_santa", voice: "bf_emma" }, loadVoices()), { voiceEs: "em_santa", voice: "bf_emma" });
    const cur = Object.freeze({ voice: "af_heart", speed: 1, mp3Kbps: 48 });
    assert.equal(mergeSettings(cur, {}).voiceEs, "ef_dora");
  });

  test("a stored voice that is no longer offered falls back to the default", () => {
    const merged = mergeSettings({ voice: "bm_lewis", voiceEs: "xx", speed: 1, mp3Kbps: 48 }, {});
    assert.deepEqual([merged.voice, merged.voiceEs], ["af_heart", "ef_dora"]);
  });

  test("DynamoDB store round-trips voiceEs", async () => {
    const put = fakeClient();
    await createDynamoStore({ client: put, tableName: "T" }).putSettings({ voice: "af_heart", voiceEs: "em_alex", speed: 1, mp3Kbps: 48 });
    assert.equal(put.calls[0].input.Item.voiceEs, "em_alex");
    const got = createDynamoStore({ client: fakeClient(() => ({ Item: { voice: "af_heart", voiceEs: "em_alex", speed: 1, mp3Kbps: 48 } })), tableName: "T" });
    assert.equal((await got.getSettings()).voiceEs, "em_alex");
  });
});

describe("language through generate and regenerate", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "lang-"));
  const ctx = await startLocalApp({ dir, config: { generatePerMinute: 100, maxConcurrentJobs: 100 } });
  after(() => ctx.close());
  const { call, started } = ctx;

  test("defaults to en, accepts es and en, and puts voiceEs in the settings snapshot", async () => {
    const lang = async (extra) => {
      const r = await call("POST", "/api/generate", { title: "T", text: TEXT, ...extra });
      assert.equal(r.status, 202);
      return started.at(-1);
    };
    assert.equal((await lang({})).language, "en");
    assert.equal((await lang({ language: "es" })).language, "es");
    assert.equal((await lang({ language: "en" })).language, "en");
    assert.equal(started.at(-1).settings.voiceEs, "ef_dora");
  });

  test("anything else is a readable 400", async () => {
    for (const language of ["fr", "ES", 5, true, {}]) {
      const r = await call("POST", "/api/generate", { title: "T", text: TEXT, language });
      assert.equal(r.status, 400, String(language));
      assert.match(r.json.error, /Language must be "en" or "es"/);
    }
  });

  test("regenerate keeps the stored language, defaulting to en", async () => {
    await mkdir(path.join(dir, "raw"), { recursive: true });
    const other = "3c781dab-4521-40d2-a9b6-ad5f2bb0ba99";
    await writeFile(path.join(dir, "raw", `${ID}.json`), JSON.stringify({ title: "Hola", content: "<p>x</p>", source: "generated", language: "es" }));
    await writeFile(path.join(dir, "raw", `${other}.json`), JSON.stringify({ title: "Old", content: "<p>x</p>" }));
    assert.equal((await call("POST", `/api/passages/${ID}/regenerate`)).status, 202);
    assert.equal(started.at(-1).language, "es");
    assert.equal((await call("POST", `/api/passages/${other}/regenerate`)).status, 202);
    assert.equal(started.at(-1).language, "en");
  });
});

describe("job input and passages carry language", () => {
  test("buildJobInput includes language, defaulting to en and coercing junk to en", () => {
    const base = { passageId: ID, title: "T", content: "c", source: "generated", settings: { voiceEs: "ef_dora" }, pronunciations: {} };
    assert.equal(buildJobInput({ ...base, language: "es" }).language, "es");
    assert.equal(buildJobInput(base).language, "en");
    assert.equal(buildJobInput({ ...base, language: "xx" }).language, "en");
    assert.equal(buildJobInput(base).settings.voiceEs, "ef_dora");
  });

  test("summarizePassage reads language from the timing document", () => {
    const at = (timing) => summarizePassage({ id: ID, timing, mtimeMs: 0 }).language;
    assert.deepEqual([at({ language: "es" }), at({}), at({ language: "fr" })], ["es", "en", "en"]);
  });

  test("file catalog and GET /api/passages expose Passage.language", async () => {
    const dir = await mkdtemp(path.join(tmpdir(), "cat-"));
    await writeFile(path.join(dir, `${ID}.timing.json`), JSON.stringify({ title: "Hola", language: "es", words: [] }));
    await writeFile(path.join(dir, "3c781dab-4521-40d2-a9b6-ad5f2bb0ba99.timing.json"), JSON.stringify({ title: "Hi", words: [] }));
    const ctx = await startLocalApp({ dir });
    const list = (await ctx.call("GET", "/api/passages")).json.data;
    assert.deepEqual(Object.fromEntries(list.map((p) => [p.title, p.language])), { Hola: "es", Hi: "en" });
    ctx.close();
  });

  test("dynamo catalog defaults missing language to en", async () => {
    const items = [
      { pk: "PASSAGE", sk: "a", title: "A", createdAt: "2026-02-01", language: "es" },
      { pk: "PASSAGE", sk: "b", title: "B", createdAt: "2026-01-01" },
    ];
    const catalog = createDynamoCatalog({ client: fakeClient(() => ({ Items: items })), tableName: "T" });
    assert.deepEqual((await catalog.list()).map((p) => [p.id, p.language]), [["a", "es"], ["b", "en"]]);
  });

  test("seed stores language on the PASSAGE item", async () => {
    const dir = await mkdtemp(path.join(tmpdir(), "seedlang-"));
    await writeFile(path.join(dir, `${ID}.timing.json`), JSON.stringify({ title: "Hola", language: "es", words: [] }));
    await writeFile(path.join(dir, `${ID}.mp3`), "x");
    const ddb = fakeClient();
    await seed({ s3: fakeClient(), ddb, bucket: "B", tableName: "T", dataDir: dir, logger: quiet });
    assert.equal(ddb.calls[0].input.Item.language, "es");
  });
});
