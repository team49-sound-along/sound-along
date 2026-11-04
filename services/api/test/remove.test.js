import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, test } from "node:test";
import { gunzipSync, gzipSync } from "node:zlib";
import { removePassages } from "../scripts/remove.js";
import { readIndex, seed } from "../scripts/seed.js";

const quiet = { info() {}, warn() {}, error() {} };
const id = (n) => `00000000-0000-4000-8000-00000000000${n}`;
const entry = (n, extra = {}) => ({ id: id(n), title: `P${n}`, createdAt: `2026-11-0${n}T00:00:00Z`, ...extra });

/** An in-memory S3: objects by key, list (two per page), delete, get and put. The commands are told apart by their input fields. */
function memoryS3(objects) {
  const store = new Map(Object.entries(objects));
  return {
    store,
    async send(cmd) {
      const i = cmd.input;
      const name = cmd.constructor.name;
      if (name === "ListObjectsV2Command") {
        const keys = [...store.keys()].filter((k) => k.startsWith(i.Prefix)).sort().filter((k) => !i.ContinuationToken || k > i.ContinuationToken);
        return { Contents: keys.slice(0, 2).map((Key) => ({ Key })), ...(keys.length > 2 ? { NextContinuationToken: keys[1] } : {}) };
      }
      if (name === "DeleteObjectsCommand") { i.Delete.Objects.forEach((o) => store.delete(o.Key)); return {}; }
      if (name === "GetObjectCommand") {
        if (!store.has(i.Key)) throw Object.assign(new Error("NoSuchKey"), { name: "NoSuchKey" });
        const body = Buffer.from(store.get(i.Key));
        return { Body: { transformToByteArray: async () => new Uint8Array(body) } };
      }
      if (name === "PutObjectCommand") { store.set(i.Key, i.Body); return {}; }
      throw new Error(`unexpected command ${name}`);
    },
  };
}
const ddbRecorder = () => ({ deleted: [], async send(cmd) { if (cmd.constructor.name === "DeleteCommand") this.deleted.push(cmd.input.Key); return {}; } });
const indexOf = (s3) => JSON.parse(gunzipSync(Buffer.from(s3.store.get("data/index.json"))).toString("utf8"));

function site() {
  const index = [entry(1, { translations: { es: id(2) } }), entry(2, { translationOf: id(1) }), entry(3)];
  const objects = { "data/index.json": gzipSync(JSON.stringify(index)) };
  for (const n of [1, 2, 3]) for (const ext of ["mp3", "timing.json", "cards.json", "word-park-aaaaaaaa.png"]) objects[`data/${id(n)}.${ext}`] = Buffer.from("x");
  return memoryS3(objects);
}

describe("removing passages from a deployed site", () => {
  test("a dry run lists what would go and changes nothing", async () => {
    const s3 = site(), ddb = ddbRecorder();
    const out = await removePassages({ s3, ddb, bucket: "B", tableName: "T", ids: [id(3)], logger: quiet });
    assert.deepEqual(out.problems, []);
    assert.equal(out.keys.length, 4);
    assert.equal(s3.store.size, 13);
    assert.deepEqual(ddb.deleted, []);
  });

  test("apply deletes every file of the passage (following the listing across pages), its summary, and its line in the Library list, and nothing else", async () => {
    const s3 = site(), ddb = ddbRecorder();
    const out = await removePassages({ s3, ddb, bucket: "B", tableName: "T", ids: [id(3)], apply: true, logger: quiet });
    assert.deepEqual(out.problems, []);
    assert.deepEqual([...s3.store.keys()].filter((k) => k.includes(id(3))), []);
    assert.equal([...s3.store.keys()].filter((k) => k.includes(id(1))).length, 4, "the others are untouched");
    assert.deepEqual(ddb.deleted, [{ pk: "PASSAGE", sk: id(3) }]);
    assert.deepEqual(indexOf(s3).map((p) => p.id), [id(1), id(2)]);
  });

  test("a passage and its translation go together; removing only one is refused so no link is left pointing nowhere", async () => {
    const s3 = site(), ddb = ddbRecorder();
    const refused = await removePassages({ s3, ddb, bucket: "B", tableName: "T", ids: [id(1)], apply: true, logger: quiet });
    assert.ok(refused.problems.length >= 1 && refused.problems.some((p) => p.includes(id(2))));
    assert.equal(s3.store.size, 13, "nothing was deleted");
    const ok = await removePassages({ s3, ddb, bucket: "B", tableName: "T", ids: [id(1), id(2)], apply: true, logger: quiet });
    assert.deepEqual(ok.problems, []);
    assert.deepEqual(indexOf(s3).map((p) => p.id), [id(3)]);
  });

  test("a wrong id or a malformed id is refused before anything happens", async () => {
    const s3 = site(), ddb = ddbRecorder();
    assert.ok((await removePassages({ s3, ddb, bucket: "B", tableName: "T", ids: [id(9)], apply: true, logger: quiet })).problems[0].includes("not in the Library list"));
    assert.ok((await removePassages({ s3, ddb, bucket: "B", tableName: "T", ids: ["../etc"], apply: true, logger: quiet })).problems[0].includes("not a passage id"));
    assert.ok((await removePassages({ s3, ddb, bucket: "B", tableName: "T", ids: [], logger: quiet })).problems.length);
    assert.equal(s3.store.size, 13);
  });
});

describe("seeding adds and refreshes, and never hides what is already listed", () => {
  test("a passage already in the Library list that is not being seeded stays in it", async () => {
    const existing = [entry(7, { title: "A teacher's own passage" })];
    const s3 = memoryS3({ "data/index.json": gzipSync(JSON.stringify(existing)) });
    const dir = await mkdtemp(path.join(tmpdir(), "seed-merge-"));
    await writeFile(path.join(dir, `${id(5)}.timing.json`), JSON.stringify({ title: "Seeded", words: [], metrics: {} }));
    await writeFile(path.join(dir, `${id(5)}.mp3`), "mp3");
    const ids = await seed({ s3, ddb: ddbRecorder(), bucket: "B", tableName: "T", dataDir: dir, logger: quiet });
    assert.deepEqual(ids, [id(5)]);
    assert.deepEqual(new Set(indexOf(s3).map((p) => p.id)), new Set([id(7), id(5)]));
  });

  test("a seeded passage replaces its own older line instead of appearing twice, and a missing list is an empty one", async () => {
    const s3 = memoryS3({ "data/index.json": gzipSync(JSON.stringify([entry(5, { title: "Old title" })])) });
    const dir = await mkdtemp(path.join(tmpdir(), "seed-merge-"));
    await writeFile(path.join(dir, `${id(5)}.timing.json`), JSON.stringify({ title: "New title", words: [], metrics: {} }));
    await writeFile(path.join(dir, `${id(5)}.mp3`), "mp3");
    await seed({ s3, ddb: ddbRecorder(), bucket: "B", tableName: "T", dataDir: dir, logger: quiet });
    assert.deepEqual(indexOf(s3).map((p) => p.title), ["New title"]);
    assert.deepEqual(await readIndex({ s3: memoryS3({}), bucket: "B" }), []);
  });
});
