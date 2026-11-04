import assert from "node:assert/strict";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, test } from "node:test";
import { createDynamoStore } from "../src/aws/dynamoStore.js";
import { createFileStore } from "../src/stores/fileStore.js";
import { READER_SESSIONS, RETENTION_DAYS } from "../src/stores/fileReadAloud.js";
import { fakeClient } from "./support/harness.js";

const NOW = Date.parse("2026-11-04T10:00:00Z"); // a Wednesday: its week starts Monday 2026-11-02
const result = (over = {}) => ({ passageId: "p1", classId: "c1", language: "en", wordsTotal: 100, wordsRead: 80, finished: false, retried: 0, words: [{ i: 3, kind: "skipped" }, { i: 9, kind: "differs" }], readerCode: null, ...over });
const newFileStore = async () => createFileStore(path.join(await mkdtemp(path.join(tmpdir(), "sa-ra-")), "state.json"));

describe("file store: read-aloud counters", () => {
  test("counts sessions, finishes, retries and per word misses, per passage and class", async () => {
    const store = await newFileStore();
    await store.recordReadAloud(result({ finished: true, wordsRead: 100, words: [] }), NOW);
    await store.recordReadAloud(result({ retried: 2 }), NOW);
    await store.recordReadAloud(result({ classId: null }), NOW);
    const sums = await store.readAloudSummaries();
    assert.deepEqual(sums.find((s) => s.classId === "c1"), { passageId: "p1", classId: "c1", sessions: 2, finished: 1, retried: 1 });
    assert.equal(sums.find((s) => s.classId === null).sessions, 1);
    const words = (await store.readAloudWords("p1")).find((g) => g.classId === "c1");
    assert.deepEqual(words.words, { 3: { s: 1, d: 0 }, 9: { s: 0, d: 1 } });
  });
  test("keeps no session list and no reader entry without a reader code", async () => {
    const store = await newFileStore();
    await store.recordReadAloud(result(), NOW);
    assert.deepEqual(await store.readAloudReaders("c1"), []);
    assert.ok(!JSON.stringify(await store.readAloudSummaries()).includes("readerCode"));
  });
  test("weekly totals are bucketed by Monday and old weeks expire", async () => {
    const store = await newFileStore();
    await store.recordReadAloud(result(), NOW);
    await store.recordReadAloud(result(), NOW - 7 * 86_400_000);
    assert.deepEqual((await store.readAloudWeeks("2026-10-26")).map((w) => [w.week, w.sessions]).sort(), [["2026-10-26", 1], ["2026-11-02", 1]]);
    assert.equal((await store.readAloudWeeks("2026-11-02")).length, 1);
    await store.recordReadAloud(result({ passageId: "p2" }), NOW + (RETENTION_DAYS + 30) * 86_400_000);
    assert.equal((await store.readAloudWeeks("2000-01-03")).length, 1);
  });
  test("a reader code keeps only the last sessions, as a day, a percentage and two counts", async () => {
    const store = await newFileStore();
    for (let n = 0; n < READER_SESSIONS + 3; n += 1) await store.recordReadAloud(result({ readerCode: "K7Q29XMA", wordsRead: 50 + n }), NOW);
    const [reader] = await store.readAloudReaders("c1");
    assert.equal(reader.code, "K7Q29XMA");
    assert.equal(reader.sessions.length, READER_SESSIONS);
    assert.deepEqual(Object.keys(reader.sessions[0]).sort(), ["at", "differs", "finished", "pct", "skipped"]);
    assert.equal(reader.words[3].s, READER_SESSIONS + 3);
  });
  test("class settings are stored per class and as a default", async () => {
    const store = await newFileStore();
    await store.putClassSettings("DEFAULT", { share: false });
    await store.putClassSettings("c1", { mic: false });
    await store.putClassSettings("c1", { readers: true });
    assert.deepEqual(await store.getClassSettings(), { DEFAULT: { share: false }, c1: { mic: false, readers: true } });
  });
});

describe("dynamo store: read-aloud counters", () => {
  const store = (respond) => {
    const client = fakeClient(respond);
    return { client, store: createDynamoStore({ client, tableName: "T" }) };
  };

  test("one session adds to flat counters, with a ttl, and never writes a list or a name", async () => {
    const { client, store: s } = store();
    await s.recordReadAloud(result());
    const names = client.calls.map((c) => `${c.input.Key.pk}|${c.input.Key.sk}`);
    assert.ok(names.includes("RA_SUMMARY|p1#c1"));
    assert.ok(names.some((n) => n.startsWith("RA_WEEK|")));
    assert.ok(names.includes("RA_WORDS#p1|c1"));
    const words = client.calls.find((c) => c.input.Key.pk === "RA_WORDS#p1").input;
    assert.deepEqual(Object.values(words.ExpressionAttributeNames).filter((v) => /_/.test(v)).sort(), ["d_9", "s_3"]);
    assert.match(words.UpdateExpression, /ADD/);
    assert.ok(client.calls.every((c) => c.input.ExpressionAttributeNames["#t"] === "ttl" && c.input.ExpressionAttributeValues[":t"] > 0));
    assert.equal(client.calls.some((c) => c.input.Key.pk.startsWith("RA_READER")), false);
  });
  test("a reader code appends to a capped list and trims it", async () => {
    const { client, store: s } = store();
    await s.recordReadAloud(result({ readerCode: "K7Q29XMA" }));
    const reader = client.calls.filter((c) => c.input.Key.pk === "RA_READER#c1");
    assert.equal(reader.length, 2);
    assert.match(reader[0].input.UpdateExpression, /list_append/);
    assert.equal(reader[1].input.ConditionExpression, "size(#s) > :max");
    assert.equal(reader[1].input.ExpressionAttributeValues[":max"], READER_SESSIONS);
  });
  test("the trim's condition failing is fine; other errors are not", async () => {
    const miss = Object.assign(new Error("x"), { name: "ConditionalCheckFailedException" });
    const ok = store((c) => { if (c.input.ConditionExpression) throw miss; return {}; });
    await ok.store.recordReadAloud(result({ readerCode: "K7Q29XMA" }));
    const boom = store((c) => { if (c.input.ConditionExpression) throw new Error("boom"); return {}; });
    await assert.rejects(boom.store.recordReadAloud(result({ readerCode: "K7Q29XMA" })), /boom/);
  });
  test("reads are capped queries and flat counters come back as word maps", async () => {
    const { client, store: s } = store((c) => {
      const pk = c.input.ExpressionAttributeValues?.[":pk"];
      if (pk === "RA_SUMMARY") return { Items: [{ pk, sk: "p1#c1", sessions: 4, finished: 2, retried: 1 }, { pk, sk: "p1#-", sessions: 1 }] };
      if (pk === "RA_WORDS#p1") return { Items: [{ pk, sk: "c1", s_3: 2, d_3: 1, ttl: 5, updatedAt: "x" }] };
      if (pk === "RA_READER#c1") return { Items: [{ pk, sk: "K7Q29XMA#p1", sessions: [{ at: "2026-11-04", pct: 80, skipped: 1, differs: 0, finished: false }], s_3: 1 }] };
      return { Items: [{ pk, sk: "2026-11-02#p1#c1", sessions: 3, finished: 1, retried: 0 }] };
    });
    assert.deepEqual((await s.readAloudSummaries()).map((x) => [x.classId, x.sessions]), [["c1", 4], [null, 1]]);
    assert.deepEqual(await s.readAloudWords("p1"), [{ passageId: "p1", classId: "c1", sessions: 4, words: { 3: { s: 2, d: 1 } } }]);
    assert.deepEqual((await s.readAloudWeeks("2026-10-05"))[0], { week: "2026-11-02", passageId: "p1", classId: "c1", sessions: 3, finished: 1, retried: 0 });
    assert.equal((await s.readAloudReaders("c1"))[0].code, "K7Q29XMA");
    for (const call of client.calls.filter((c) => c.name === "QueryCommand" && !c.input.ExpressionAttributeValues[":pk"].startsWith("RA_WORDS"))) assert.ok(call.input.Limit > 0);
  });
  test("class settings use one item per class and the default", async () => {
    const { client, store: s } = store((c) => (c.constructor.name === "QueryCommand" ? { Items: [{ pk: "CLASSSETTINGS", sk: "DEFAULT", share: false }, { pk: "CLASSSETTINGS", sk: "c1", mic: false }] } : {}));
    assert.deepEqual(await s.getClassSettings(), { DEFAULT: { share: false }, c1: { mic: false } });
    await s.putClassSettings("c1", { readers: true });
    assert.deepEqual(client.calls.at(-1).input.Key, { pk: "CLASSSETTINGS", sk: "c1" });
  });
});
