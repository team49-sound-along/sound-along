import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, before, describe, test } from "node:test";
import { createApp } from "../src/app.js";
import { createFileCatalog } from "../src/catalog.js";
import { createJobStore } from "../src/jobs/jobStore.js";
import { createFileStore } from "../src/stores/fileStore.js";

const PID = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98";
const timing = {
  id: PID,
  title: "Park Caretaker",
  engine: "kokoro",
  voice: "af_heart",
  duration_ms: 60000,
  vocab: { 1: { word: "nature", definition: "Everything not made by people." } },
  metrics: {
    characters: 1000, words: 200, audioSeconds: 60, generateSeconds: 6, unalignedWords: 2,
    estimatedLambdaUsd: 0.01, estimateBasis: "test basis",
  },
  words: [{ i: 0, text: "Hi", start_ms: 0, end_ms: 100, sentence: 0, paragraph: 0, aligned: true }],
};

let server;
let base;
let dir;
let started = [];
let generationEnabled = true;

const call = async (method, url, body) => {
  const res = await fetch(base + url, {
    method,
    headers: body === undefined ? {} : { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch { /* binary or html */ }
  return { status: res.status, json, text, headers: res.headers };
};

before(async () => {
  dir = await mkdtemp(path.join(tmpdir(), "sa-api-"));
  await writeFile(path.join(dir, `${PID}.timing.json`), JSON.stringify(timing));
  await writeFile(path.join(dir, `${PID}.mp3`), "fake-mp3-bytes");
  await writeFile(path.join(dir, "state.json"), '{"secret":true}');
  await writeFile(path.join(dir, "quality-report.json"), JSON.stringify({ generatedAt: "t", asr: { method: "m", pooled: { wer: 0.02, medianErrorMs: 40, p95ErrorMs: 190 } } }));
  const jobs = createJobStore();
  const runner = { start: async (input) => { started = [...started, input]; return jobs.create(input.title); } };
  const app = createApp({
    store: createFileStore(path.join(dir, "state.json.test")),
    catalog: createFileCatalog(dir),
    jobs,
    runner,
    config: {
      dataDir: dir, webDist: null, maxConcurrentJobs: 1, generatePerMinute: 3,
      get generationEnabled() { return generationEnabled; },
    },
    logger: { error() {} },
  });
  await new Promise((resolve) => { server = app.listen(0, "127.0.0.1", resolve); });
  base = `http://127.0.0.1:${server.address().port}`;
});
after(() => server.close());

describe("health and catalog", () => {
  test("health reports generation flag", async () => {
    const r = await call("GET", "/api/health");
    assert.equal(r.status, 200);
    assert.deepEqual(r.json.data, { status: "ok", generation: { enabled: true } });
  });
  test("passages come from the data folder", async () => {
    const { json } = await call("GET", "/api/passages");
    assert.equal(json.success, true);
    assert.equal(json.data.length, 1);
    assert.equal(json.data[0].title, "Park Caretaker");
    assert.equal(json.data[0].vocabCount, 1);
    assert.equal(json.data[0].source, "sample");
  });
  test("security headers are set", async () => {
    const r = await call("GET", "/api/health");
    assert.equal(r.headers.get("x-content-type-options"), "nosniff");
  });
});

describe("cards documents", () => {
  const OTHER = "5af24980-4d6d-41c1-87fa-4f21cb2d169d";
  test("GET /data/<id>.cards.json serves the JSON when the file exists", async () => {
    await writeFile(path.join(dir, `${PID}.cards.json`), JSON.stringify({ words: { relax: { word: "relax" } }, places: {} }));
    const r = await call("GET", `/data/${PID}.cards.json`);
    assert.equal(r.status, 200);
    assert.match(r.headers.get("content-type"), /application\/json/);
    assert.deepEqual(r.json.words.relax, { word: "relax" });
  });
  test("a text without cards answers 404 (the reader then falls back to the vocabulary)", async () => {
    assert.equal((await call("GET", `/data/${OTHER}.cards.json`)).status, 404);
  });
  test("only the exact <uuid>.cards.json name is served, and the listening answer key stays unreachable", async () => {
    for (const name of ["cards.json", `${PID}.cards.json.bak`, `${PID}.cards.JSON`, `${PID}.card.json`, "ab%2Fmanifest.json", "raw%2Fab%2Fmanifest.json", "ab/manifest.json"]) {
      assert.equal((await call("GET", `/data/${name}`)).status, 404, name);
    }
  });
});

describe("static data allow-list", () => {
  test("serves audio and timing", async () => {
    assert.equal((await call("GET", `/data/${PID}.mp3`)).status, 200);
    assert.equal((await call("GET", `/data/${PID}.timing.json`)).status, 200);
  });
  test("supports range requests", async () => {
    const res = await fetch(`${base}/data/${PID}.mp3`, { headers: { Range: "bytes=0-3" } });
    assert.equal(res.status, 206);
  });
  test("never serves state or other files", async () => {
    assert.equal((await call("GET", "/data/state.json")).status, 404);
    assert.equal((await call("GET", "/data/quality-report.json")).status, 404);
    assert.equal((await call("GET", "/data/..%2Fpackage.json")).status, 404);
  });
});

describe("assignments", () => {
  let id;
  test("rejects bad input with a readable message", async () => {
    const r = await call("POST", "/api/assignments", { passageId: "nope", classId: "cls-g3-p2", soundAlong: true });
    assert.equal(r.status, 400);
    assert.match(r.json.error, /passage/i);
    const r2 = await call("POST", "/api/assignments", { passageId: PID, classId: "cls-g3-p2", soundAlong: true, dueDate: "tomorrow" });
    assert.equal(r2.status, 400);
  });
  test("creates, lists, toggles and deletes", async () => {
    const created = await call("POST", "/api/assignments", { passageId: PID, classId: "cls-g4-p4", soundAlong: true, dueDate: "2026-11-20" });
    assert.equal(created.status, 201);
    id = created.json.data.id;
    assert.equal(created.json.data.className, "Period 4 Reading");
    assert.equal((await call("GET", "/api/assignments")).json.data.length, 1);
    const patched = await call("PATCH", `/api/assignments/${id}`, { soundAlong: false });
    assert.equal(patched.json.data.soundAlong, false);
    assert.equal((await call("DELETE", `/api/assignments/${id}`)).status, 200);
    assert.equal((await call("GET", "/api/assignments")).json.data.length, 0);
  });
  test("unknown ids return 404", async () => {
    assert.equal((await call("PATCH", "/api/assignments/missing", { soundAlong: true })).status, 404);
    assert.equal((await call("DELETE", "/api/assignments/missing")).status, 404);
  });
  test("invalid JSON is a 400, not a crash", async () => {
    const res = await fetch(`${base}/api/assignments`, { method: "POST", headers: { "content-type": "application/json" }, body: "{oops" });
    assert.equal(res.status, 400);
  });
});

describe("generate", () => {
  const text = "A short passage that is long enough to pass validation.";
  test("validates title and text", async () => {
    assert.equal((await call("POST", "/api/generate", { title: "", text })).status, 400);
    assert.equal((await call("POST", "/api/generate", { title: "T", text: "short" })).status, 400);
    assert.equal((await call("POST", "/api/generate", { title: "T", text: "x".repeat(12001) })).status, 400);
  });
  test("accepts valid input and exposes the job", async () => {
    const r = await call("POST", "/api/generate", { title: "My passage", text });
    assert.equal(r.status, 202);
    const job = await call("GET", `/api/jobs/${r.json.data.jobId}`);
    assert.equal(job.json.data.status, "queued");
    assert.equal(started.at(-1).title, "My passage");
  });
  test("one job at a time", async () => {
    const r = await call("POST", "/api/generate", { title: "Second", text });
    assert.equal(r.status, 429);
  });
  test("kill switch returns 503", async () => {
    generationEnabled = false;
    const r = await call("POST", "/api/generate", { title: "T", text });
    generationEnabled = true;
    assert.equal(r.status, 503);
  });
  test("unknown job is 404", async () => {
    assert.equal((await call("GET", "/api/jobs/none")).status, 404);
  });
});

describe("events and insights", () => {
  test("records events and rejects unknown ones", async () => {
    assert.equal((await call("POST", "/api/events", { passageId: PID, type: "play" })).status, 200);
    assert.equal((await call("POST", "/api/events", { passageId: PID, type: "word_tap" })).status, 200);
    assert.equal((await call("POST", "/api/events", { passageId: PID, type: "bogus" })).status, 400);
    assert.equal((await call("POST", "/api/events", { passageId: "x", type: "play" })).status, 400);
  });
  test("insights aggregate real metrics", async () => {
    const { json } = await call("GET", "/api/insights");
    const d = json.data;
    assert.equal(d.catalog.passages, 1);
    assert.equal(d.quality.alignedPercent, 99);
    assert.equal(d.speed.avgRealTimeFactor, 0.1);
    assert.equal(d.cost.pollyNeuralUsd, 0.016);
    assert.equal(d.cost.projectedCatalog.pollyNeuralUsd, 320);
    assert.equal(d.cost.projectedCatalog.estimatedLambdaUsd, 200);
    assert.equal(d.cost.basis, "test basis");
    assert.equal(d.quality.timingAgreement.medianErrorMs, 40);
    assert.equal(d.adoption.plays, 1);
    assert.equal(d.adoption.wordTaps, 1);
  });
});

test("unknown API route is a 404 envelope", async () => {
  const r = await call("GET", "/api/nothing");
  assert.equal(r.status, 404);
  assert.equal(r.json.success, false);
});


describe("passage index document", () => {
  test("GET /data/index.json is a plain array of public passage fields (no envelope, no internals)", async () => {
    const res = await fetch(`${base}/data/index.json`);
    assert.equal(res.status, 200);
    assert.match(res.headers.get("cache-control"), /no-cache/);
    const list = await res.json();
    assert.ok(Array.isArray(list) && list.length >= 1);
    assert.ok(list[0].id && list[0].title && "language" in list[0] && "pairId" in list[0]);
    assert.equal("metrics" in list[0] || "review" in list[0], false);
  });
});
