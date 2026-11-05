import { test } from "node:test";
import assert from "node:assert/strict";
import { gzipSync } from "node:zlib";
import { createS3Timing } from "../src/aws/s3Timing.js";

const ID = "0b7ec6b4-eaa2-524b-a4b3-989a6ca74c53";
const doc = { language: "en", words: [{ i: 0, text: "Hello", start_ms: 0 }, { i: 1, text: "there", start_ms: 300 }] };
const s3With = (body) => ({ send: async () => ({ Body: { transformToByteArray: async () => body } }) });

test("a gzip-compressed timing file, as the seed and the generator store it, is read", async () => {
  const t = await createS3Timing({ s3: s3With(gzipSync(JSON.stringify(doc))), bucket: "b" }).timing(ID);
  assert.deepEqual(t, { language: "en", words: [{ i: 0, text: "Hello" }, { i: 1, text: "there" }] });
});

test("a plain JSON timing file is read too", async () => {
  const t = await createS3Timing({ s3: s3With(Buffer.from(JSON.stringify(doc))), bucket: "b" }).timing(ID);
  assert.equal(t.words.length, 2);
});

test("a missing file or bad id gives null, never an error", async () => {
  const missing = { send: async () => { throw Object.assign(new Error("x"), { name: "NoSuchKey" }); } };
  assert.equal(await createS3Timing({ s3: missing, bucket: "b" }).timing(ID), null);
  assert.equal(await createS3Timing({ s3: s3With(Buffer.from("{}")), bucket: "b" }).timing("../etc/passwd"), null);
});
