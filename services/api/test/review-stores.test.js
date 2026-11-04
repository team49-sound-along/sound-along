import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, describe, test } from "node:test";
import { createDynamoCatalog } from "../src/aws/dynamoCatalog.js";
import { createDynamoStore } from "../src/aws/dynamoStore.js";
import { buildReviewItems } from "../src/review.js";
import { reviewOf, summarizePassage } from "../src/passageSummary.js";
import { createFileStore } from "../src/stores/fileStore.js";
import { seed } from "../scripts/seed.js";
import { fakeClient, quiet, startLocalApp } from "./support/harness.js";

const A = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98";
const B = "3c781dab-4521-40d2-a9b6-ad5f2bb0ba99";
const C = "4d781dab-4521-40d2-a9b6-ad5f2bb0ba97";
const timing = (title, suspects) => ({ title, engine: "kokoro", duration_ms: 1, metrics: {}, words: [], review: suspects && { source: "asr-check", suspects } });

describe("buildReviewItems", () => {
  const sources = [
    { id: A, title: "A", review: { source: "asr-check", suspects: [{ expected: "Gaieties", heard: "deities" }, { expected: "nave", heard: "knave" }] } },
    { id: B, title: "B", review: { suspects: [{ expected: "gaieties", heard: "deities" }] } },
    { id: C, title: "C", review: { suspects: "oops" } },
  ];
  test("drops dismissed and fixed words case-insensitively and omits empty passages", () => {
    const items = buildReviewItems({ sources, dismissed: ["NAVE"], fixed: ["gaieties"] });
    assert.deepEqual(items, []);
    const some = buildReviewItems({ sources, dismissed: ["nave"], fixed: [] });
    assert.deepEqual(some.map((i) => [i.passageId, i.suspects.map((s) => s.expected)]), [[A, ["Gaieties"]], [B, ["gaieties"]]]);
    assert.equal(some[1].source, "asr-check");
  });
});

describe("GET /api/review and dismiss (file catalog)", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "review-"));
  await writeFile(path.join(dir, `${A}.timing.json`), JSON.stringify(timing("Alpha", [{ expected: "gaieties", heard: "deities" }, { expected: "nave", heard: "knave" }])));
  await writeFile(path.join(dir, `${B}.timing.json`), JSON.stringify(timing("Beta", [{ expected: "nave", heard: "knave" }])));
  await writeFile(path.join(dir, `${C}.timing.json`), JSON.stringify(timing("Gamma", null)));
  const ctx = await startLocalApp({ dir });
  after(() => ctx.server.close());
  const { call } = ctx;

  test("lists suspects per passage, then hides fixed and dismissed words everywhere", async () => {
    const first = (await call("GET", "/api/review")).json.data;
    assert.deepEqual(first.map((i) => i.title).sort(), ["Alpha", "Beta"]);
    assert.deepEqual(first.find((i) => i.title === "Alpha").suspects[0], { expected: "gaieties", heard: "deities" });
    await call("PUT", "/api/pronunciations/gaieties", { respelling: "gay-uh-teez" });
    const afterFix = (await call("GET", "/api/review")).json.data;
    assert.deepEqual(afterFix.find((i) => i.title === "Alpha").suspects.map((s) => s.expected), ["nave"]);
    const d = await call("POST", "/api/review/dismiss", { word: "NAVE" });
    assert.deepEqual(d.json.data, { word: "nave" });
    assert.deepEqual((await call("GET", "/api/review")).json.data, []);
    assert.equal((await call("POST", "/api/review/dismiss", { word: "nave" })).status, 200, "idempotent");
  });

  test("dismiss validates the word", async () => {
    for (const body of [{}, { word: "" }, { word: "a b" }, { word: 3 }]) {
      const r = await call("POST", "/api/review/dismiss", body);
      assert.equal(r.status, 400);
      assert.match(r.json.error, /word/i);
    }
  });

  test("the public Passage list never carries review", async () => {
    const list = (await call("GET", "/api/passages")).json.data;
    assert.ok(list.length === 3 && list.every((p) => p.review === undefined));
  });
});

describe("passage source comes from raw/<id>.json", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "src-"));
  await mkdir(path.join(dir, "raw"));
  for (const id of [A, B, C]) await writeFile(path.join(dir, `${id}.timing.json`), JSON.stringify(timing(id, null)));
  await writeFile(path.join(dir, "raw", `${A}.json`), JSON.stringify({ source: "sample" }));
  await writeFile(path.join(dir, "raw", `${B}.json`), JSON.stringify({ source: "generated" }));
  const ctx = await startLocalApp({ dir });
  after(() => ctx.server.close());

  test("sample with a raw file is still sample; missing raw defaults to sample", async () => {
    const bySource = Object.fromEntries((await ctx.call("GET", "/api/passages")).json.data.map((p) => [p.id, p.source]));
    assert.deepEqual(bySource, { [A]: "sample", [B]: "generated", [C]: "sample" });
  });

  test("summarizePassage and the seed script use the same rule", async () => {
    assert.equal(summarizePassage({ id: A, timing: {}, mtimeMs: 0, source: "generated" }).source, "generated");
    assert.equal(summarizePassage({ id: A, timing: {}, mtimeMs: 0 }).source, "sample");
    const ddb = fakeClient();
    await writeFile(path.join(dir, `${A}.mp3`), "a");
    await writeFile(path.join(dir, `${B}.mp3`), "b");
    await writeFile(path.join(dir, `${B}.timing.json`), JSON.stringify(timing("B", [{ expected: "x", heard: "y" }])));
    await seed({ s3: fakeClient(), ddb, bucket: "B", tableName: "T", dataDir: dir, logger: quiet });
    const items = Object.fromEntries(ddb.calls.map((c) => [c.input.Item.sk, c.input.Item]));
    assert.equal(items[A].source, "sample");
    assert.equal(items[B].source, "generated");
    assert.equal(items[A].review, undefined);
    assert.deepEqual(items[B].review, { source: "asr-check", suspects: [{ expected: "x", heard: "y" }] });
    assert.equal(reviewOf({}), undefined);
  });
});

describe("file store v2", () => {
  const fresh = async () => createFileStore(path.join(await mkdtemp(path.join(tmpdir(), "fs-")), "state.json"));

  test("settings round-trip and persist across instances", async () => {
    const file = path.join(await mkdtemp(path.join(tmpdir(), "fs-")), "state.json");
    const store = createFileStore(file);
    assert.equal(await store.getSettings(), null);
    await store.putSettings({ voice: "af_heart", speed: 1, mp3Kbps: 32 });
    assert.deepEqual(await createFileStore(file).getSettings(), { voice: "af_heart", speed: 1, mp3Kbps: 32 });
  });

  test("pronunciations: create/replace/list/delete, dismissed is a set", async () => {
    const store = await fresh();
    assert.equal((await store.putPronunciation("b", "bee")).created, true);
    assert.equal((await store.putPronunciation("a", "ay")).created, true);
    const again = await store.putPronunciation("a", "ey");
    assert.equal(again.created, false);
    assert.deepEqual((await store.listPronunciations()).map((p) => [p.word, p.respelling]), [["a", "ey"], ["b", "bee"]]);
    assert.equal(await store.deletePronunciation("a"), true);
    assert.equal(await store.deletePronunciation("a"), false);
    await store.addDismissed("x");
    await store.addDismissed("x");
    assert.deepEqual(await store.listDismissed(), ["x"]);
    assert.deepEqual(await store.eventCounts(), { plays: 0, wordTaps: 0, completions: 0 });
  });
});

describe("dynamo store v2", () => {
  test("settings live at SETTINGS/CURRENT; absent means null", async () => {
    const put = fakeClient();
    await createDynamoStore({ client: put, tableName: "T" }).putSettings({ voice: "v", speed: 1, mp3Kbps: 48 });
    const { Item } = put.calls[0].input;
    assert.deepEqual([put.calls[0].name, Item.pk, Item.sk, Item.voice, Item.speed, Item.mp3Kbps], ["PutCommand", "SETTINGS", "CURRENT", "v", 1, 48]);
    assert.equal(await createDynamoStore({ client: fakeClient(), tableName: "T" }).getSettings(), null);
    const got = createDynamoStore({ client: fakeClient(() => ({ Item: { pk: "SETTINGS", sk: "CURRENT", voice: "v", speed: 1, mp3Kbps: 48, updatedAt: "t" } })), tableName: "T" });
    assert.deepEqual(await got.getSettings(), { voice: "v", speed: 1, mp3Kbps: 48 });
    const withEngine = createDynamoStore({ client: fakeClient(() => ({ Item: { pk: "SETTINGS", sk: "CURRENT", voice: "v", speed: 1, mp3Kbps: 48, ttsEngine: "polly" } })), tableName: "T" });
    assert.equal((await withEngine.getSettings()).ttsEngine, "polly");
  });

  test("pronunciations use PRONUNCIATION/{word}; created is false when an item was replaced", async () => {
    const client = fakeClient((c) => (c.input.ReturnValues === "ALL_OLD" && c.constructor.name === "PutCommand" && c.input.Item.sk === "old" ? { Attributes: { sk: "old" } } : {}));
    const store = createDynamoStore({ client, tableName: "T" });
    assert.equal((await store.putPronunciation("new", "nyoo")).created, true);
    assert.equal((await store.putPronunciation("old", "ohld")).created, false);
    assert.deepEqual([client.calls[0].input.Item.pk, client.calls[0].input.Item.sk, client.calls[0].input.Item.respelling], ["PRONUNCIATION", "new", "nyoo"]);
    const del = createDynamoStore({ client: fakeClient(() => ({ Attributes: { sk: "w" } })), tableName: "T" });
    assert.equal(await del.deletePronunciation("w"), true);
    assert.equal(await createDynamoStore({ client: fakeClient(), tableName: "T" }).deletePronunciation("w"), false);
  });

  test("lists are sorted and stripped of keys; dismissed uses DISMISSED/{word}", async () => {
    const client = fakeClient((c) => (c.input.ExpressionAttributeValues[":pk"] === "PRONUNCIATION"
      ? { Items: [{ pk: "PRONUNCIATION", sk: "b", respelling: "bee", updatedAt: "t" }, { pk: "PRONUNCIATION", sk: "a", respelling: "ay", updatedAt: "t" }] }
      : { Items: [{ pk: "DISMISSED", sk: "x" }] }));
    const store = createDynamoStore({ client, tableName: "T" });
    assert.deepEqual(await store.listPronunciations(), [{ word: "a", respelling: "ay", updatedAt: "t" }, { word: "b", respelling: "bee", updatedAt: "t" }]);
    assert.deepEqual(await store.listDismissed(), ["x"]);
    const put = fakeClient();
    await createDynamoStore({ client: put, tableName: "T" }).addDismissed("nave");
    assert.deepEqual([put.calls[0].input.Item.pk, put.calls[0].input.Item.sk], ["DISMISSED", "nave"]);
  });
});

describe("dynamo catalog review", () => {
  const items = [
    { pk: "PASSAGE", sk: A, id: A, title: "A", createdAt: "2026-01-01", metrics: {}, review: { source: "asr-check", suspects: [{ expected: "x", heard: "y" }] } },
    { pk: "PASSAGE", sk: B, id: B, title: "B", createdAt: "2026-01-02", metrics: {} },
  ];
  test("reviewSources come from the item's review field, and list() does not expose it", async () => {
    const catalog = createDynamoCatalog({ client: fakeClient(() => ({ Items: items })), tableName: "T" });
    const sources = await catalog.reviewSources();
    assert.deepEqual(sources.map((s) => [s.id, s.title]), [[A, "A"]]);
    assert.ok((await catalog.list()).every((p) => !("review" in p)));
    assert.deepEqual(buildReviewItems({ sources, dismissed: [], fixed: [] })[0].suspects, [{ expected: "x", heard: "y" }]);
  });
});
