import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, test } from "node:test";
import { createApp } from "../src/app.js";
import { HttpError } from "../src/http.js";
import { createDynamoCatalog } from "../src/aws/dynamoCatalog.js";
import { createDynamoJobs } from "../src/aws/dynamoJobs.js";
import { createDynamoStore } from "../src/aws/dynamoStore.js";
import { createSfnRunner } from "../src/aws/sfnRunner.js";
import { seed } from "../scripts/seed.js";

/** Fake client: records commands and answers with `respond(command)` (sync or async). */
function fakeClient(respond = () => ({})) {
  const calls = [];
  return {
    calls,
    async send(command) {
      calls.push({ name: command.constructor.name, input: command.input });
      return respond(command, calls.length);
    },
  };
}
const quiet = { error() {}, warn() {}, info() {} };

describe("dynamoStore", () => {
  test("create writes an ASSIGNMENT item and list is newest first without keys", async () => {
    const client = fakeClient((c) => (c.constructor.name === "QueryCommand"
      ? { Items: [
          { pk: "ASSIGNMENT", sk: "a", id: "a", createdAt: "2026-01-01T00:00:00Z" },
          { pk: "ASSIGNMENT", sk: "b", id: "b", createdAt: "2026-02-01T00:00:00Z" },
        ] }
      : {}));
    const store = createDynamoStore({ client, tableName: "T" });
    const created = await store.createAssignment({ passageId: "p", soundAlong: true });
    const put = client.calls[0];
    assert.equal(put.name, "PutCommand");
    assert.deepEqual([put.input.Item.pk, put.input.Item.sk], ["ASSIGNMENT", created.id]);
    assert.ok(created.createdAt);
    const list = await store.listAssignments();
    assert.deepEqual(list.map((a) => a.id), ["b", "a"]);
    assert.equal(list[0].pk, undefined);
  });

  test("update uses a condition and returns null on a miss", async () => {
    const miss = Object.assign(new Error("x"), { name: "ConditionalCheckFailedException" });
    const client = fakeClient(() => { throw miss; });
    const store = createDynamoStore({ client, tableName: "T" });
    assert.equal(await store.updateAssignment("nope", { soundAlong: false }), null);
    assert.equal(client.calls[0].input.ConditionExpression, "attribute_exists(pk)");
    const hit = createDynamoStore({ client: fakeClient(() => ({ Attributes: { pk: "ASSIGNMENT", sk: "a", id: "a", soundAlong: false } })), tableName: "T" });
    assert.deepEqual(await hit.updateAssignment("a", { soundAlong: false }), { id: "a", soundAlong: false });
  });

  test("update rethrows other errors", async () => {
    const store = createDynamoStore({ client: fakeClient(() => { throw new Error("boom"); }), tableName: "T" });
    await assert.rejects(store.updateAssignment("a", { soundAlong: true }), /boom/);
  });

  test("delete reports whether the item existed", async () => {
    const existed = fakeClient(() => ({ Attributes: { id: "a" } }));
    assert.equal(await createDynamoStore({ client: existed, tableName: "T" }).deleteAssignment("a"), true);
    assert.equal(existed.calls[0].input.ReturnValues, "ALL_OLD");
    assert.equal(await createDynamoStore({ client: fakeClient(), tableName: "T" }).deleteAssignment("a"), false);
  });

  test("recordEvent uses an atomic ADD and counts default to zero", async () => {
    const client = fakeClient();
    const store = createDynamoStore({ client, tableName: "T" });
    await store.recordEvent("word_tap");
    const { input } = client.calls[0];
    assert.equal(input.UpdateExpression, "ADD #n :one");
    assert.equal(input.ExpressionAttributeNames["#n"], "wordTaps");
    assert.deepEqual(input.Key, { pk: "EVENTS", sk: "TOTALS" });
    assert.deepEqual(await store.eventCounts(), { plays: 0, wordTaps: 0, completions: 0 });
    const some = createDynamoStore({ client: fakeClient(() => ({ Item: { plays: 3 } })), tableName: "T" });
    assert.deepEqual(await some.eventCounts(), { plays: 3, wordTaps: 0, completions: 0 });
  });

  test("lists the synthetic classes", async () => {
    assert.ok((await createDynamoStore({ client: fakeClient(), tableName: "T" }).listClasses()).length > 0);
  });
});

describe("dynamoCatalog", () => {
  const page = (items, next) => ({ Items: items, LastEvaluatedKey: next });
  const item = (id, createdAt) => ({ pk: "PASSAGE", sk: id, id, title: id, createdAt, metrics: { words: 5 }, engine: "kokoro" });

  test("quality report comes from the QUALITY item, or null when absent", async () => {
    const present = createDynamoCatalog({ client: fakeClient(() => ({ Item: { report: { asr: { pooled: { wer: 0.02 } } } } })), tableName: "T" });
    assert.deepEqual(await present.qualityReport(), { asr: { pooled: { wer: 0.02 } } });
    const absent = createDynamoCatalog({ client: fakeClient(() => ({})), tableName: "T" });
    assert.equal(await absent.qualityReport(), null);
  });

  test("paginates, shapes list and timings, and caches for 30 s", async () => {
    let clock = 1000;
    const client = fakeClient((c, n) => (n === 1 ? page([item("a", "2026-01-01")], { sk: "a" }) : page([item("b", "2026-02-01")])));
    const catalog = createDynamoCatalog({ client, tableName: "T", now: () => clock });
    const list = await catalog.list();
    assert.deepEqual(list.map((p) => p.id), ["b", "a"]);
    assert.equal(list[0].metrics, undefined);
    assert.equal(list[0].pk, undefined);
    assert.deepEqual(client.calls[1].input.ExclusiveStartKey, { sk: "a" });
    assert.deepEqual(await catalog.timings(), [
      { engine: "kokoro", metrics: { words: 5 } },
      { engine: "kokoro", metrics: { words: 5 } },
    ]);
    assert.equal(client.calls.length, 2, "second call served from cache");
    clock += 31_000;
    await catalog.list();
    assert.equal(client.calls.length, 3, "cache expired, queried again");
  });
});

describe("dynamoJobs", () => {
  test("create stores a queued job with a 7-day ttl", async () => {
    const client = fakeClient();
    const jobs = createDynamoJobs({ client, tableName: "T", now: () => 2_000_000 });
    const job = await jobs.create("Title");
    const { Item } = client.calls[0].input;
    assert.equal(job.status, "queued");
    assert.equal(job.ttl, undefined);
    assert.equal(Item.ttl, 2000 + 7 * 86400);
    assert.deepEqual([Item.pk, Item.sk], ["JOB", job.id]);
  });

  test("get strips keys and ttl, and returns null when missing", async () => {
    const found = createDynamoJobs({ client: fakeClient(() => ({ Item: { pk: "JOB", sk: "j", id: "j", ttl: 1, status: "done" } })), tableName: "T" });
    assert.deepEqual(await found.get("j"), { id: "j", status: "done" });
    assert.equal(await createDynamoJobs({ client: fakeClient(), tableName: "T" }).get("x"), null);
  });

  test("update is conditional and returns null for an unknown job", async () => {
    const miss = Object.assign(new Error("x"), { name: "ConditionalCheckFailedException" });
    const client = fakeClient(() => { throw miss; });
    assert.equal(await createDynamoJobs({ client, tableName: "T" }).update("x", { step: "align" }), null);
    assert.equal(client.calls[0].input.ConditionExpression, "attribute_exists(pk)");
    const ok = createDynamoJobs({ client: fakeClient(() => ({ Attributes: { pk: "JOB", sk: "j", id: "j", step: "align", ttl: 5 } })), tableName: "T" });
    assert.deepEqual(await ok.update("j", { step: "align" }), { id: "j", step: "align" });
  });

  test("activeCount sums COUNT pages filtered on queued/running", async () => {
    const client = fakeClient((c, n) => (n === 1 ? { Count: 1, LastEvaluatedKey: { sk: "x" } } : { Count: 2 }));
    const jobs = createDynamoJobs({ client, tableName: "T" });
    assert.equal(await jobs.activeCount(), 3);
    const { input } = client.calls[0];
    assert.equal(input.Select, "COUNT");
    assert.equal(input.ExpressionAttributeValues[":pk"], "JOB");
    assert.deepEqual([input.ExpressionAttributeValues[":queued"], input.ExpressionAttributeValues[":running"]], ["queued", "running"]);
  });
});

describe("sfnRunner", () => {
  const makeJobs = () => {
    const updates = [];
    return {
      updates,
      create: async (title) => ({ id: "job-1", title, status: "queued" }),
      update: async (id, patch) => { updates.push(patch); return { id, ...patch }; },
    };
  };

  test("writes raw input then starts the execution", async () => {
    const jobs = makeJobs();
    const s3 = fakeClient();
    const sfn = fakeClient();
    const runner = createSfnRunner({ jobs, s3, sfn, bucket: "B", stateMachineArn: "arn:sm", logger: quiet });
    const job = await runner.start({ title: "T", text: "One.\nTwo <b>." });
    const put = s3.calls[0];
    assert.equal(put.name, "PutObjectCommand");
    assert.equal(put.input.Bucket, "B");
    const raw = JSON.parse(put.input.Body);
    assert.equal(put.input.Key, `raw/${raw.uuid}.json`);
    assert.equal(raw.content, "<p>One.</p>\n<p>Two &lt;b&gt;.</p>");
    assert.equal(raw.source, "generated");
    const exec = sfn.calls[0];
    assert.equal(exec.name, "StartExecutionCommand");
    assert.equal(exec.input.stateMachineArn, "arn:sm");
    assert.deepEqual(JSON.parse(exec.input.input), { jobId: "job-1", passageId: raw.uuid, title: "T", rawKey: put.input.Key });
    assert.equal(job.passageId, raw.uuid);
  });

  test("marks the job failed and throws 503 when StartExecution fails", async () => {
    const jobs = makeJobs();
    const sfn = fakeClient(() => { throw new Error("denied"); });
    const runner = createSfnRunner({ jobs, s3: fakeClient(), sfn, bucket: "B", stateMachineArn: "arn", logger: quiet });
    await assert.rejects(runner.start({ title: "T", text: "x" }), (err) => err instanceof HttpError && err.status === 503);
    assert.equal(jobs.updates[0].status, "failed");
    assert.match(jobs.updates[0].error, /could not start/);
  });
});

describe("lambda handler", () => {
  test("GET /api/health through a Function URL v2 event returns the envelope", async () => {
    Object.assign(process.env, { AWS_REGION: "us-west-2", AWS_ACCESS_KEY_ID: "x", AWS_SECRET_ACCESS_KEY: "x" });
    const { createHandler } = await import("../src/aws/lambda.js");
    const clients = { ddb: fakeClient(), s3: fakeClient(), sfn: fakeClient() };
    const handler = createHandler({ GENERATION_ENABLED: "false", TABLE_NAME: "T", BUCKET: "B" }, clients);
    const event = {
      version: "2.0", routeKey: "$default", rawPath: "/api/health", rawQueryString: "",
      headers: { host: "x.lambda-url.us-west-2.on.aws", "x-forwarded-for": "1.2.3.4" },
      requestContext: { http: { method: "GET", path: "/api/health", protocol: "HTTP/1.1", sourceIp: "1.2.3.4", userAgent: "t" }, stage: "$default" },
      isBase64Encoded: false,
    };
    const res = await handler(event, { awsRequestId: "r" });
    assert.equal(res.statusCode, 200);
    assert.deepEqual(JSON.parse(res.body), { success: true, data: { status: "ok", generation: { enabled: false } }, error: null, meta: {} });
    assert.equal(clients.ddb.calls.length, 0);
  });
});

describe("/data route without dataDir", () => {
  test("returns 404 JSON without touching disk", async () => {
    const app = createApp({ config: { generatePerMinute: 1, maxConcurrentJobs: 1 }, store: {}, catalog: {}, jobs: {}, runner: {}, logger: quiet });
    const server = app.listen(0);
    try {
      const res = await fetch(`http://127.0.0.1:${server.address().port}/data/2b781dab-4521-40d2-a9b6-ad5f2bb0ba98.mp3`);
      assert.equal(res.status, 404);
      assert.equal((await res.json()).success, false);
    } finally {
      server.close();
    }
  });
});

describe("seed script", () => {
  test("uploads files with content types and writes PASSAGE items", async () => {
    const dir = await mkdtemp(path.join(tmpdir(), "seed-"));
    const id = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98";
    await writeFile(path.join(dir, `${id}.mp3`), "audio");
    await writeFile(path.join(dir, `${id}.timing.json`), JSON.stringify({ title: "Park", duration_ms: 10, metrics: { words: 7 }, vocab: { 1: {} } }));
    await mkdir(path.join(dir, "raw"));
    const s3 = fakeClient();
    const ddb = fakeClient();
    const ids = await seed({ s3, ddb, bucket: "B", tableName: "T", dataDir: dir, logger: quiet });
    assert.deepEqual(ids, [id]);
    assert.deepEqual(s3.calls.map((c) => [c.input.Key, c.input.ContentType]), [[`data/${id}.mp3`, "audio/mpeg"], [`data/${id}.timing.json`, "application/json"]]);
    const { Item } = ddb.calls[0].input;
    assert.deepEqual([Item.pk, Item.sk, Item.title, Item.words, Item.source, Item.vocabCount], ["PASSAGE", id, "Park", 7, "sample", 1]);
    assert.deepEqual(Item.metrics, { words: 7 });
  });
});
