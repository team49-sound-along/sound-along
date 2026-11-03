import assert from "node:assert/strict";
import { setTimeout as sleep } from "node:timers/promises";
import { after, describe, test } from "node:test";
import { createApp } from "../src/app.js";
import { createDynamoJobs } from "../src/aws/dynamoJobs.js";
import { createJobStore } from "../src/jobs/jobStore.js";
import { createRateLimiter } from "../src/rateLimit.js";

const text = "A short passage that is long enough to pass validation.";
const servers = [];
after(() => servers.forEach((s) => s.close()));

/** App whose job registry answers asynchronously, like DynamoDB, so check-then-start can interleave. */
async function startApp({ config, runnerDelayMs = 20 }) {
  const memory = createJobStore();
  const jobs = {
    ...memory,
    activeCount: async () => { await sleep(5); return memory.activeCount(); },
    acquireStartLock: async () => memory.acquireStartLock(),
  };
  const runner = { start: async ({ title }) => { await sleep(runnerDelayMs); return jobs.create(title); } };
  const app = createApp({
    store: {}, catalog: { list: async () => [] }, jobs, runner,
    config: { generationEnabled: true, maxConcurrentJobs: 1, generatePerMinute: 100, ...config },
    logger: { error() {} },
  });
  const server = await new Promise((resolve) => { const s = app.listen(0, "127.0.0.1", () => resolve(s)); });
  servers.push(server);
  return `http://127.0.0.1:${server.address().port}`;
}

const generate = (base, headers = {}) =>
  fetch(`${base}/api/generate`, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify({ title: "T", text }),
  });

describe("concurrency cap is atomic", () => {
  test("five simultaneous requests start exactly one job", async () => {
    const base = await startApp({ config: {} });
    const statuses = (await Promise.all(Array.from({ length: 5 }, () => generate(base)))).map((r) => r.status);
    assert.equal(statuses.filter((s) => s === 202).length, 1, `statuses: ${statuses}`);
    assert.equal(statuses.filter((s) => s === 429).length, 4, `statuses: ${statuses}`);
  });

  test("the start lock is released when starting fails", async () => {
    const memory = createJobStore();
    const release = memory.acquireStartLock();
    assert.equal(memory.acquireStartLock(), null);
    release();
    assert.equal(typeof memory.acquireStartLock(), "function");
  });
});

describe("dynamo start lock", () => {
  const fakeClient = (handler) => {
    const calls = [];
    return { calls, send: async (command) => { calls.push(command); return handler(command, calls.length); } };
  };

  test("acquire is a conditional put that treats an expired lease as free", async () => {
    const client = fakeClient(() => ({}));
    const jobs = createDynamoJobs({ client, tableName: "T", now: () => 5_000_000 });
    assert.equal(typeof (await jobs.acquireStartLock()), "function");
    const { input } = client.calls[0];
    assert.deepEqual([input.Item.pk, input.Item.sk], ["LOCK", "GENERATE_START"]);
    assert.match(input.ConditionExpression, /attribute_not_exists\(pk\) OR expiresAt < :now/);
    assert.ok(input.Item.expiresAt > 5_000_000);
    assert.ok(input.Item.ttl > 0);
  });

  test("returns null when someone else holds the lease", async () => {
    const held = Object.assign(new Error("x"), { name: "ConditionalCheckFailedException" });
    const jobs = createDynamoJobs({ client: fakeClient(() => { throw held; }), tableName: "T" });
    assert.equal(await jobs.acquireStartLock(), null);
  });

  test("release only deletes the lock it owns", async () => {
    const client = fakeClient(() => ({}));
    const jobs = createDynamoJobs({ client, tableName: "T" });
    const release = await jobs.acquireStartLock();
    await release();
    const del = client.calls[1].input;
    assert.deepEqual(del.Key, { pk: "LOCK", sk: "GENERATE_START" });
    assert.match(del.ConditionExpression, /owner = :owner/);
    assert.equal(del.ExpressionAttributeValues[":owner"], client.calls[0].input.Item.owner);
  });

  test("a failed release never throws into the request", async () => {
    let n = 0;
    const client = fakeClient(() => { if (++n === 2) throw new Error("boom"); return {}; });
    const release = await createDynamoJobs({ client, tableName: "T" }).acquireStartLock();
    await assert.doesNotReject(release());
  });
});

describe("client IP for rate limiting", () => {
  test("a forged leading X-Forwarded-For cannot dodge the limit when one proxy hop is trusted", async () => {
    const base = await startApp({ config: { trustProxy: 1, generatePerMinute: 1, maxConcurrentJobs: 99 } });
    const first = await generate(base, { "x-forwarded-for": "9.9.9.9, 5.5.5.5" });
    const second = await generate(base, { "x-forwarded-for": "8.8.8.8, 5.5.5.5" });
    assert.equal(first.status, 202);
    assert.equal(second.status, 429);
  });
});

describe("rate limiter memory", () => {
  test("expired keys are evicted", () => {
    let t = 0;
    const allow = createRateLimiter({ max: 1, windowMs: 1000, now: () => t });
    allow("a"); allow("b");
    assert.equal(allow.size(), 2);
    t = 5000;
    allow("c");
    assert.equal(allow.size(), 1);
  });
});
