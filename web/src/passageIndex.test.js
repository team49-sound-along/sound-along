import assert from "node:assert/strict";
import { test } from "node:test";
import { passageIndex } from "./api.js";

const ok = (body) => async () => ({ ok: true, status: 200, json: async () => body });

test("reads the index document when it exists", async () => {
  const list = [{ id: "a", title: "A" }];
  assert.deepEqual(await passageIndex(ok(list)), list);
});

test("asks for a fresh copy so a newly generated passage shows up", async () => {
  let options;
  await passageIndex(async (_url, opts) => ((options = opts), { ok: true, json: async () => [] }));
  assert.equal(options.cache, "no-cache");
});

test("falls back to the API when the document is missing, malformed or the request fails", async () => {
  const calls = [];
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    calls.push(url);
    return { ok: true, status: 200, json: async () => ({ success: true, data: [{ id: "api" }], error: null, meta: {} }) };
  };
  try {
    assert.deepEqual(await passageIndex(async () => ({ ok: false, status: 404 })), [{ id: "api" }]);
    assert.deepEqual(await passageIndex(ok({ not: "an array" })), [{ id: "api" }]);
    assert.deepEqual(await passageIndex(async () => { throw new Error("offline"); }), [{ id: "api" }]);
    assert.equal(calls.filter((u) => u === "/api/passages").length, 3);
  } finally {
    globalThis.fetch = realFetch;
  }
});
