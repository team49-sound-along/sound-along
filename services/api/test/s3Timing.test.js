import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { createS3Timing } from "../src/aws/s3Timing.js";
import { fakeClient } from "./support/harness.js";

const ID = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98";
const body = (doc) => ({ Body: { transformToString: async () => JSON.stringify(doc), transformToByteArray: async () => Buffer.from(JSON.stringify(doc)) } });

describe("s3Timing", () => {
  test("reads data/<id>.timing.json once, keeps only language and words, and caches", async () => {
    const s3 = fakeClient(() => body({ language: "es", words: [{ i: 0, text: "hola", start_ms: 1, secret: "x" }], metrics: {} }));
    const t = createS3Timing({ s3, bucket: "B" });
    const doc = await t.timing(ID);
    assert.deepEqual(doc, { language: "es", words: [{ i: 0, text: "hola" }] });
    await t.timing(ID);
    assert.equal(s3.calls.length, 1);
    assert.equal(s3.calls[0].input.Key, `data/${ID}.timing.json`);
  });
  test("a bad id never reaches S3, a missing file is null and other errors surface", async () => {
    const s3 = fakeClient(() => { throw Object.assign(new Error("x"), { name: "NoSuchKey" }); });
    const t = createS3Timing({ s3, bucket: "B" });
    assert.equal(await t.timing("../raw/secret"), null);
    assert.equal(s3.calls.length, 0);
    assert.equal(await t.timing(ID), null);
    const boom = createS3Timing({ s3: fakeClient(() => { throw new Error("boom"); }), bucket: "B" });
    await assert.rejects(boom.timing(ID), /boom/);
  });
});
