import assert from "node:assert/strict";
import { request } from "node:http";
import { readFile, readdir, stat } from "node:fs/promises";
import path from "node:path";
import { after, describe, test } from "node:test";
import { createS3Recordings } from "../src/aws/s3Recordings.js";
import { MAX_RECORDING_BYTES } from "../src/recordings/rules.js";
import { fakeClient, startLocalApp } from "./support/harness.js";

const ctx = await startLocalApp();
after(() => ctx.server.close());
const { call, base, dataDir } = ctx;
const valid = { filename: "read.mp3", contentType: "audio/mpeg", size: 1000 };

const put = (url, body, headers = {}) => fetch(base + url, { method: "PUT", headers: { "content-type": "audio/mpeg", ...headers }, body });

/** Raw PUT with chunked streaming and no Content-Length, so only the streaming cap can stop it. */
function chunkedPut(url, chunks, chunkSize) {
  return new Promise((resolve) => {
    const u = new URL(base + url);
    const req = request({ host: u.hostname, port: u.port, path: u.pathname, method: "PUT", headers: { "content-type": "audio/mpeg" } }, (res) => {
      res.resume();
      res.on("end", () => resolve(res.statusCode));
    });
    req.on("error", () => undefined);
    let sent = 0;
    const write = () => {
      while (sent < chunks) {
        sent += 1;
        if (!req.write(Buffer.alloc(chunkSize))) return void req.once("drain", write);
      }
      return req.end();
    };
    write();
  });
}

describe("POST /api/recordings (local)", () => {
  test("returns an id and a local upload target", async () => {
    const r = await call("POST", "/api/recordings", valid);
    assert.equal(r.status, 201);
    const { recordingId, upload } = r.json.data;
    assert.match(recordingId, /^[0-9a-f-]{36}$/);
    assert.deepEqual(upload, { method: "PUT", url: `/api/recordings/${recordingId}/content`, headers: { "Content-Type": "audio/mpeg" } });
  });

  test("rejects bad input with readable messages", async () => {
    const cases = [
      [{ ...valid, contentType: "video/mp4" }, /MP3|audio/i],
      [{ ...valid, filename: "" }, /file name/i],
      [{ ...valid, filename: "x".repeat(121) }, /file name/i],
      [{ ...valid, size: MAX_RECORDING_BYTES + 1 }, /25 MB/],
      [{ ...valid, size: 0 }, /empty/i],
      [{ ...valid, size: "big" }, /empty/i],
      [[], /JSON object/i],
    ];
    for (const [body, pattern] of cases) {
      const r = await call("POST", "/api/recordings", body);
      assert.equal(r.status, 400, JSON.stringify(body).slice(0, 80));
      assert.match(r.json.error, pattern);
    }
    assert.equal((await call("POST", "/api/recordings", { ...valid, size: MAX_RECORDING_BYTES })).status, 201);
  });
});

describe("PUT /api/recordings/:id/content (local)", () => {
  test("streams the raw body to <dataDir>/raw/<id>.audio and returns 204", async () => {
    const { recordingId, upload } = (await call("POST", "/api/recordings", valid)).json.data;
    const bytes = Buffer.from("RIFF-fake-audio-bytes");
    const res = await put(upload.url, bytes);
    assert.equal(res.status, 204);
    assert.deepEqual(await readFile(path.join(dataDir, "raw", `${recordingId}.audio`)), bytes);
  });

  test("a JSON content type is still stored raw, never parsed", async () => {
    const { upload, recordingId } = (await call("POST", "/api/recordings", valid)).json.data;
    const res = await put(upload.url, '{"not":"parsed"}', { "content-type": "application/json" });
    assert.equal(res.status, 204);
    assert.equal(await readFile(path.join(dataDir, "raw", `${recordingId}.audio`), "utf8"), '{"not":"parsed"}');
  });

  test("unknown or malformed ids are 404 and write nothing", async () => {
    const before = await readdir(path.join(dataDir, "raw"));
    for (const id of ["2b781dab-4521-40d2-a9b6-ad5f2bb0ba98", "not-a-uuid", "..%2F..%2Fstate"]) {
      const res = await put(`/api/recordings/${id}/content`, "abc");
      assert.equal(res.status, 404, id);
      assert.equal((await res.json()).success, false);
    }
    assert.deepEqual(await readdir(path.join(dataDir, "raw")), before);
  });

  test("a declared size over 25 MB is refused up front", async () => {
    const { upload } = (await call("POST", "/api/recordings", valid)).json.data;
    const status = await new Promise((resolve) => {
      const u = new URL(base + upload.url);
      const req = request({ host: u.hostname, port: u.port, path: u.pathname, method: "PUT", headers: { "content-length": String(MAX_RECORDING_BYTES + 1) } }, (res) => {
        res.resume();
        resolve(res.statusCode);
      });
      req.on("error", () => resolve("reset"));
      req.flushHeaders();
    });
    assert.equal(status, 413);
  });

  test("a chunked body over 25 MB is cut off while streaming and leaves no file behind", async () => {
    const { upload, recordingId } = (await call("POST", "/api/recordings", valid)).json.data;
    const status = await chunkedPut(upload.url, 27, 1024 * 1024);
    assert.equal(status, 413);
    const files = await readdir(path.join(dataDir, "raw"));
    assert.ok(!files.some((f) => f.startsWith(recordingId) && (f.endsWith(".audio") || f.endsWith(".part"))), files.join(","));
  });

  test("an empty body is a 400", async () => {
    const { upload } = (await call("POST", "/api/recordings", valid)).json.data;
    const res = await put(upload.url, "");
    assert.equal(res.status, 400);
    assert.match((await res.json()).error, /empty/i);
  });

  test("a body of exactly 25 MB is accepted", async () => {
    const { upload, recordingId } = (await call("POST", "/api/recordings", valid)).json.data;
    const res = await put(upload.url, Buffer.alloc(MAX_RECORDING_BYTES));
    assert.equal(res.status, 204);
    assert.equal((await stat(path.join(dataDir, "raw", `${recordingId}.audio`))).size, MAX_RECORDING_BYTES);
  });
});

describe("kill switch and rate limit on recordings", () => {
  test("503 when generation is off, 429 past the write limit", async () => {
    const off = await startLocalApp({ config: { generationEnabled: false } });
    const limited = await startLocalApp({ config: { writePerMinute: 1 } });
    try {
      assert.equal((await off.call("POST", "/api/recordings", valid)).status, 503);
      assert.equal((await limited.call("POST", "/api/recordings", valid)).status, 201);
      assert.equal((await limited.call("POST", "/api/recordings", valid)).status, 429);
    } finally {
      off.server.close();
      limited.server.close();
    }
  });
});

describe("S3 recordings", () => {
  test("presigns a PUT for raw/<id>.audio with the content type and a size cap", async () => {
    const seen = [];
    const recordings = createS3Recordings({ s3: fakeClient(), bucket: "B", presign: async (command, opts) => { seen.push({ command, opts }); return "https://s3.example/signed"; } });
    const out = await recordings.create({ filename: "a.mp3", contentType: "audio/mpeg", size: 5000 });
    assert.deepEqual(out.upload, { method: "PUT", url: "https://s3.example/signed", headers: { "Content-Type": "audio/mpeg" } });
    const { input } = seen[0].command;
    assert.deepEqual([input.Bucket, input.Key, input.ContentType, input.ContentLength], ["B", `raw/${out.recordingId}.audio`, "audio/mpeg", 5000]);
    assert.ok(seen[0].opts.expiresIn > 0);
    assert.deepEqual(recordings.ref(out.recordingId), { key: `raw/${out.recordingId}.audio` });
  });

  test("exists uses HeadObject: 404 means no, other errors surface", async () => {
    const id = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98";
    const yes = createS3Recordings({ s3: fakeClient(() => ({})), bucket: "B", presign: async () => "" });
    assert.equal(await yes.exists(id), true);
    const no = createS3Recordings({ s3: fakeClient(() => { throw Object.assign(new Error("x"), { name: "NotFound" }); }), bucket: "B", presign: async () => "" });
    assert.equal(await no.exists(id), false);
    assert.equal(await no.exists("../x"), false);
    const boom = createS3Recordings({ s3: fakeClient(() => { throw new Error("denied"); }), bucket: "B", presign: async () => "" });
    await assert.rejects(boom.exists(id), /denied/);
  });

  test("the route works with the S3 adapter and has no local upload route", async () => {
    const { createApp } = await import("../src/app.js");
    const recordings = createS3Recordings({ s3: fakeClient(), bucket: "B", presign: async () => "https://s3.example/x" });
    const app = createApp({ config: { generationEnabled: true, generatePerMinute: 1 }, store: {}, catalog: {}, jobs: {}, runner: {}, recordings, logger: { error() {} } });
    const server = await new Promise((r) => { const s = app.listen(0, "127.0.0.1", () => r(s)); });
    try {
      const b = `http://127.0.0.1:${server.address().port}`;
      const res = await fetch(`${b}/api/recordings`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(valid) });
      assert.equal(res.status, 201);
      assert.equal((await res.json()).data.upload.url, "https://s3.example/x");
      const local = await fetch(`${b}/api/recordings/2b781dab-4521-40d2-a9b6-ad5f2bb0ba98/content`, { method: "PUT", body: "x" });
      assert.equal(local.status, 404);
    } finally {
      server.close();
    }
  });
});
