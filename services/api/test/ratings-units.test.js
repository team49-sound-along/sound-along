import assert from "node:assert/strict";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, test } from "node:test";
import { createDynamoStore } from "../src/aws/dynamoStore.js";
import { cleanManifest, createFileManifest, createS3Manifest } from "../src/ratings/manifest.js";
import { summarizeRatings } from "../src/ratings/summary.js";
import { buildTrial } from "../src/ratings/trial.js";
import { createFileStore } from "../src/stores/fileStore.js";
import { seed, seedAb } from "../scripts/seed.js";
import { fakeClient, quiet } from "./support/harness.js";

const rating = (over) => ({ trialId: "t", passageId: "p", comparison: "ai vs human", preferredKind: "ai", kindA: "ai", kindB: "human", ratingA: 4, ratingB: 2, raterId: null, createdAt: "2026-01-01T00:00:00Z", ...over });

describe("summarizeRatings", () => {
  test("is all zeros and nulls for no ratings", () => {
    const s = summarizeRatings([]);
    assert.deepEqual([s.raters, s.ratings, s.meanRating.ai], [0, 0, null]);
  });

  test("counts, preferences, distinct raters and means (hand computed)", () => {
    const r = "11111111-1111-4111-8111-111111111111";
    const s = summarizeRatings([
      rating({ raterId: r }), // ai 4, human 2
      rating({ raterId: r, kindA: "human", kindB: "ai", ratingA: 5, ratingB: 1, preferredKind: "human" }), // human 5, ai 1
      rating({ comparison: "ai vs polly_current", kindB: "polly_current", preferredKind: "tie", ratingA: 3, ratingB: 3 }), // anonymous
      rating({ comparison: "ai vs polly_current", kindB: "polly_current", preferredKind: "polly_current", ratingA: 2, ratingB: 5 }), // anonymous
    ]);
    assert.deepEqual([s.ratings, s.raters], [4, 3]);
    assert.deepEqual(s.comparisons, [
      { comparison: "ai vs human", n: 2, preferredAi: 1, preferredOther: 1, tie: 0 },
      { comparison: "ai vs polly_current", n: 2, preferredAi: 0, preferredOther: 1, tie: 1 },
    ]);
    // ai: 4,1,3,2 = 2.5; human: 2,5 = 3.5; polly: 3,5 = 4
    assert.deepEqual(s.meanRating, { ai: 2.5, human: 3.5, polly_current: 4 });
  });

  test("rounds means to two decimals", () => {
    const s = summarizeRatings([rating({ ratingA: 1 }), rating({ ratingA: 1 }), rating({ ratingA: 2 })]);
    assert.equal(s.meanRating.ai, 1.33);
  });
});

describe("buildTrial", () => {
  const clips = [
    { token: "aaaaaaaaaaaaaaaa", passageId: "p", title: "T", kind: "ai" },
    { token: "bbbbbbbbbbbbbbbb", passageId: "p", title: "T", kind: "human" },
  ];
  test("random below 0.5 puts the AI clip first; at or above puts it second", () => {
    const first = buildTrial(clips, () => 0, () => "id");
    assert.deepEqual([first.trialId, first.a.token, first.b.token], ["id", "aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"]);
    const second = buildTrial(clips, () => 0.99, () => "id");
    assert.equal(second.a.token, "bbbbbbbbbbbbbbbb");
  });
});

describe("manifest readers", () => {
  test("cleanManifest drops malformed entries", () => {
    assert.deepEqual(cleanManifest("x"), []);
    const kept = cleanManifest([{ token: "0123456789abcdef", passageId: "p", kind: "ai" }, { token: "ZZ", passageId: "p", kind: "ai" }, { token: "0123456789abcdef", kind: "ai" }]);
    assert.deepEqual(kept, [{ token: "0123456789abcdef", passageId: "p", title: "Untitled passage", kind: "ai" }]);
  });

  test("file manifest reads <dataDir>/ab/manifest.json; missing or broken is empty", async () => {
    const dir = await mkdtemp(path.join(tmpdir(), "man-"));
    const m = createFileManifest(dir);
    assert.deepEqual(await m.read(), []);
    await mkdir(path.join(dir, "ab"));
    await writeFile(path.join(dir, "ab", "manifest.json"), "{not json");
    assert.deepEqual(await m.read(), []);
    await writeFile(path.join(dir, "ab", "manifest.json"), JSON.stringify([{ token: "0123456789abcdef", passageId: "p", title: "T", kind: "human" }]));
    assert.equal((await m.read()).length, 1);
  });

  test("S3 manifest reads raw/ab/manifest.json once per 60 s", async () => {
    let now = 1000;
    const body = { transformToString: async () => JSON.stringify([{ token: "0123456789abcdef", passageId: "p", title: "T", kind: "ai" }]) };
    const s3 = fakeClient(() => ({ Body: body }));
    const m = createS3Manifest({ s3, bucket: "B", now: () => now });
    assert.equal((await m.read()).length, 1);
    now += 59_000;
    await m.read();
    assert.equal(s3.calls.length, 1);
    assert.deepEqual([s3.calls[0].name, s3.calls[0].input], ["GetObjectCommand", { Bucket: "B", Key: "raw/ab/manifest.json" }]);
    now += 2_000;
    await m.read();
    assert.equal(s3.calls.length, 2);
  });

  test("S3 manifest: missing object is empty (and cached); other errors propagate", async () => {
    const miss = fakeClient(() => { throw Object.assign(new Error("x"), { name: "NoSuchKey" }); });
    const m = createS3Manifest({ s3: miss, bucket: "B" });
    assert.deepEqual(await m.read(), []);
    await m.read();
    assert.equal(miss.calls.length, 1);
    const denied = createS3Manifest({ s3: fakeClient(() => { throw new Error("denied"); }), bucket: "B" });
    await assert.rejects(denied.read(), /denied/);
  });
});

describe("rating stores", () => {
  test("file store persists ratings in state.json across instances", async () => {
    const file = path.join(await mkdtemp(path.join(tmpdir(), "rs-")), "state.json");
    const store = createFileStore(file);
    assert.deepEqual(await store.listRatings(), []);
    await store.addRating(rating({ trialId: "one" }));
    await store.addRating(rating({ trialId: "two", raterId: "r" }));
    const again = await createFileStore(file).listRatings();
    assert.deepEqual(again.map((r) => r.trialId), ["one", "two"]);
    assert.equal(again[1].raterId, "r");
  });

  test("dynamo store writes RATING/<uuid> and lists the partition without keys", async () => {
    const put = fakeClient();
    await createDynamoStore({ client: put, tableName: "T" }).addRating(rating());
    const { name, input } = put.calls[0];
    assert.equal(name, "PutCommand");
    assert.equal(input.Item.pk, "RATING");
    assert.match(input.Item.sk, /^[0-9a-f-]{36}$/);
    assert.deepEqual(
      ["trialId", "passageId", "comparison", "preferredKind", "kindA", "kindB", "ratingA", "ratingB", "raterId", "createdAt"].filter((k) => !(k in input.Item)),
      [],
    );
    const q = fakeClient(() => ({ Items: [{ pk: "RATING", sk: "x", ...rating({ trialId: "q" }) }] }));
    const listed = await createDynamoStore({ client: q, tableName: "T" }).listRatings();
    assert.equal(q.calls[0].input.ExpressionAttributeValues[":pk"], "RATING");
    assert.deepEqual([listed.length, listed[0].trialId, "pk" in listed[0], "sk" in listed[0]], [1, "q", false, false]);
  });
});

describe("seed uploads the blind-test files", () => {
  test("clips as audio/mpeg, manifest as application/json, others skipped", async () => {
    const dir = await mkdtemp(path.join(tmpdir(), "seed-ab-"));
    await mkdir(path.join(dir, "ab"));
    await writeFile(path.join(dir, "ab", "0123456789abcdef.mp3"), "a");
    await writeFile(path.join(dir, "ab", "fedcba9876543210.mp3"), "b");
    await writeFile(path.join(dir, "ab", "manifest.json"), "[]");
    await writeFile(path.join(dir, "ab", "notes.txt"), "x");
    const s3 = fakeClient();
    const keys = await seedAb({ s3, bucket: "B", dataDir: dir, logger: quiet });
    assert.deepEqual(keys, ["data/ab/0123456789abcdef.mp3", "data/ab/fedcba9876543210.mp3", "raw/ab/manifest.json"]);
    assert.deepEqual(s3.calls.map((c) => [c.input.Key, c.input.ContentType]), [
      ["data/ab/0123456789abcdef.mp3", "audio/mpeg"],
      ["data/ab/fedcba9876543210.mp3", "audio/mpeg"],
      ["raw/ab/manifest.json", "application/json"],
    ]);
  });

  test("seed() runs it, and a missing ab folder uploads nothing", async () => {
    const dir = await mkdtemp(path.join(tmpdir(), "seed-ab-"));
    const s3 = fakeClient();
    assert.deepEqual(await seed({ s3, ddb: fakeClient(), bucket: "B", tableName: "T", dataDir: dir, logger: quiet }), []);
    assert.equal(s3.calls.length, 0);
    await mkdir(path.join(dir, "ab"));
    await writeFile(path.join(dir, "ab", "manifest.json"), "[]");
    await seed({ s3, ddb: fakeClient(), bucket: "B", tableName: "T", dataDir: dir, logger: quiet });
    assert.equal(s3.calls[0].input.Key, "raw/ab/manifest.json");
  });
});
