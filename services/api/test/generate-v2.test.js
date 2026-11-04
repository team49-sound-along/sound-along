import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, describe, test } from "node:test";
import { createS3Sources } from "../src/aws/s3Sources.js";
import { createSfnRunner } from "../src/aws/sfnRunner.js";
import { createJobStore } from "../src/jobs/jobStore.js";
import { createLocalRunner } from "../src/jobs/localRunner.js";
import { TEXT, fakeClient, quiet, startLocalApp } from "./support/harness.js";

const PID = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98";
const ctx = await startLocalApp();
after(() => ctx.server.close());
const { call, started, dataDir, jobs } = ctx;
/** Mark every job done by id so the one-job guard frees up. */
const done = (jobId) => jobs.update(jobId, { status: "done" });
const upload = async (bytes = "audio-bytes") => {
  const { upload: target, recordingId } = (await call("POST", "/api/recordings", { filename: "a.mp3", contentType: "audio/mpeg", size: 100 })).json.data;
  await fetch(ctx.base + target.url, { method: "PUT", headers: { "content-type": "audio/mpeg" }, body: bytes });
  return recordingId;
};

describe("generate with settings snapshot", () => {
  test("snapshots current settings and pronunciations, no recording", async () => {
    await call("PUT", "/api/settings", { speed: 1.05, mp3Kbps: 64 });
    await call("PUT", "/api/pronunciations/gaieties", { respelling: "gay-uh-teez" });
    const r = await call("POST", "/api/generate", { title: "T1", text: TEXT });
    assert.equal(r.status, 202);
    const spec = started.at(-1);
    assert.deepEqual(spec.settings, { voice: "af_heart", voiceEs: "ef_dora", speed: 1.05, mp3Kbps: 64, ttsEngine: "kokoro" });
    assert.deepEqual(spec.pronunciations, { gaieties: "gay-uh-teez" });
    assert.equal(spec.recordingId, null);
    assert.equal(spec.humanPassageId, null);
    const job = (await call("GET", `/api/jobs/${r.json.data.jobId}`)).json.data;
    assert.equal(job.humanPassageId, null);
    done(r.json.data.jobId);
  });

  test("a known recording gets a new humanPassageId reported on the job", async () => {
    const recordingId = await upload();
    const r = await call("POST", "/api/generate", { title: "T2", text: TEXT, recordingId });
    assert.equal(r.status, 202);
    const spec = started.at(-1);
    assert.equal(spec.recordingId, recordingId);
    assert.match(spec.humanPassageId, /^[0-9a-f-]{36}$/);
    const job = (await call("GET", `/api/jobs/${r.json.data.jobId}`)).json.data;
    assert.equal(job.humanPassageId, spec.humanPassageId);
    done(r.json.data.jobId);
  });

  test("unknown, malformed and never-uploaded recording ids are 400", async () => {
    const issued = (await call("POST", "/api/recordings", { filename: "a.mp3", contentType: "audio/mpeg", size: 10 })).json.data.recordingId;
    for (const recordingId of [PID, "nope", 12, issued]) {
      const r = await call("POST", "/api/generate", { title: "T", text: TEXT, recordingId });
      assert.equal(r.status, 400, String(recordingId));
      assert.match(r.json.error, /recording/i);
    }
    assert.equal(jobs.activeCount(), 0, "failed checks start nothing and release the lock");
  });
});

describe("regenerate", () => {
  const writeSource = async (id, body) => {
    await mkdir(path.join(dataDir, "raw"), { recursive: true });
    await writeFile(path.join(dataDir, "raw", `${id}.json`), JSON.stringify(body));
  };

  test("404 with a friendly message when no source is stored or the id is malformed", async () => {
    for (const id of [PID, "not-a-uuid", "..%2Fstate"]) {
      const r = await call("POST", `/api/passages/${id}/regenerate`);
      assert.equal(r.status, 404, id);
      assert.match(r.json.error, /no saved source/i);
    }
    await writeSource("11111111-1111-4111-8111-111111111111", { uuid: "x" });
    assert.equal((await call("POST", "/api/passages/11111111-1111-4111-8111-111111111111/regenerate")).status, 404);
  });

  test("re-snapshots current settings for the SAME passage id and keeps stored fields", async () => {
    await writeSource(PID, {
      uuid: PID, title: "Stored", content: "<p>Hi.</p>", source: "sample",
      settings: { voice: "old", speed: 1, mp3Kbps: 24 }, pronunciations: { old: "x" },
      recording: { path: "/x/y.audio" }, humanPassageId: "33333333-3333-4333-8333-333333333333",
    });
    await call("PUT", "/api/settings", { speed: 0.8 });
    const r = await call("POST", `/api/passages/${PID}/regenerate`);
    assert.equal(r.status, 202);
    const spec = started.at(-1);
    assert.equal(spec.passageId, PID);
    assert.deepEqual([spec.title, spec.content, spec.source], ["Stored", "<p>Hi.</p>", "sample"]);
    assert.equal(spec.settings.speed, 0.8);
    assert.deepEqual(spec.pronunciations, { gaieties: "gay-uh-teez" });
    assert.deepEqual(spec.recording, { path: "/x/y.audio" });
    assert.equal(spec.humanPassageId, "33333333-3333-4333-8333-333333333333");
    done(r.json.data.jobId);
  });

  test("shares the one-job guard, rate limit and kill switch with generate", async () => {
    const busy = await call("POST", "/api/generate", { title: "A", text: TEXT });
    assert.equal(busy.status, 202);
    assert.equal((await call("POST", `/api/passages/${PID}/regenerate`)).status, 429);
    done(busy.json.data.jobId);
    const off = await startLocalApp({ config: { generationEnabled: false } });
    const slow = await startLocalApp({ config: { generatePerMinute: 1, maxConcurrentJobs: 9 } });
    try {
      assert.equal((await off.call("POST", `/api/passages/${PID}/regenerate`)).status, 503);
      await mkdir(path.join(slow.dataDir, "raw"), { recursive: true });
      await writeFile(path.join(slow.dataDir, "raw", `${PID}.json`), JSON.stringify({ title: "T", content: "<p>x</p>" }));
      assert.equal((await slow.call("POST", `/api/passages/${PID}/regenerate`)).status, 202);
      assert.equal((await slow.call("POST", `/api/passages/${PID}/regenerate`)).status, 429);
      assert.equal((await slow.call("POST", "/api/generate", { title: "T", text: TEXT })).status, 429, "same limiter");
    } finally {
      off.server.close();
      slow.server.close();
    }
  });
});

describe("local runner", () => {
  test("writes the job input file and spawns the python command", async () => {
    const dir = await mkdtemp(path.join(tmpdir(), "runner-"));
    const script = path.join(dir, "fake.mjs");
    await writeFile(script, 'console.log(JSON.stringify({step:"align"}));console.log(JSON.stringify({result:{id:"x"}}));');
    const store = createJobStore();
    const runner = createLocalRunner({ jobs: store, dataDir: dir, python: process.execPath, script, logger: quiet });
    const settings = { voice: "af_heart", speed: 0.95, mp3Kbps: 48 };
    const job = await runner.start({ title: "T", text: "One.\nTwo.", settings, pronunciations: { a: "b" }, recordingId: PID, humanPassageId: "h-1" });
    assert.equal(job.humanPassageId, "h-1");
    const raw = JSON.parse(await readFile(path.join(dir, "raw", `${store.get(job.id).passageId}.json`), "utf8"));
    assert.deepEqual(raw, {
      uuid: store.get(job.id).passageId, title: "T", content: "<p>One.</p>\n<p>Two.</p>", source: "generated", language: "en",
      settings, pronunciations: { a: "b" }, recording: { path: path.join(dir, "raw", `${PID}.audio`) }, humanPassageId: "h-1", qualityCheck: true,
    });
    for (let i = 0; i < 50 && store.get(job.id).status !== "done"; i += 1) await new Promise((r) => setTimeout(r, 20));
    assert.equal(store.get(job.id).status, "done");
  });

  test("without a recording humanPassageId is null; regenerate reuses the passage id", async () => {
    const dir = await mkdtemp(path.join(tmpdir(), "runner-"));
    const script = path.join(dir, "fake.mjs");
    await writeFile(script, "");
    const runner = createLocalRunner({ jobs: createJobStore(), dataDir: dir, python: process.execPath, script, logger: quiet });
    const job = await runner.start({ title: "T", content: "<p>x</p>", passageId: PID, source: "sample", settings: {}, pronunciations: {}, humanPassageId: "ignored" });
    assert.equal(job.humanPassageId, null);
    const raw = JSON.parse(await readFile(path.join(dir, "raw", `${PID}.json`), "utf8"));
    assert.deepEqual([raw.uuid, raw.source, raw.recording, raw.humanPassageId], [PID, "sample", null, null]);
  });
});

describe("aws runner and sources", () => {
  test("writes the same job input to S3 and passes humanPassageId to the execution", async () => {
    const s3 = fakeClient();
    const sfn = fakeClient();
    const jobs2 = { create: async (title, extra) => ({ id: "j", title, ...extra }), update: async (id, patch) => ({ id, ...patch }) };
    const runner = createSfnRunner({ jobs: jobs2, s3, sfn, bucket: "B", stateMachineArn: "arn", logger: quiet });
    const settings = { voice: "af_heart", speed: 0.95, mp3Kbps: 48 };
    await runner.start({ title: "T", text: TEXT, settings, pronunciations: {}, recordingId: PID, humanPassageId: "h-1" });
    const raw = JSON.parse(s3.calls[0].input.Body);
    assert.deepEqual(raw.recording, { key: `raw/${PID}.audio` });
    assert.deepEqual([raw.humanPassageId, raw.qualityCheck, raw.settings], ["h-1", true, settings]);
    assert.equal(JSON.parse(sfn.calls[0].input.input).parts[0].humanPassageId, "h-1");
    await runner.start({ title: "T", content: "<p>x</p>", passageId: PID, settings, pronunciations: {} });
    assert.equal(s3.calls[1].input.Key, `raw/${PID}.json`);
  });

  test("S3 sources parse the object, and a missing key is null", async () => {
    const body = { transformToString: async () => JSON.stringify({ title: "T" }) };
    assert.deepEqual(await createS3Sources({ s3: fakeClient(() => ({ Body: body })), bucket: "B" }).read(PID), { title: "T" });
    const missing = fakeClient(() => { throw Object.assign(new Error("x"), { name: "NoSuchKey" }); });
    assert.equal(await createS3Sources({ s3: missing, bucket: "B" }).read(PID), null);
    assert.equal(missing.calls.length, 1);
  });
});
