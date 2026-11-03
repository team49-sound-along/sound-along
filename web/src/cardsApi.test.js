import { test } from "node:test";
import assert from "node:assert/strict";
import { fetchCards } from "./api.js";

const respond = (status, body) => async () => ({ ok: status >= 200 && status < 300, status, json: async () => body });

test("fetchCards reads the static cards document for the passage", async () => {
  let url = "";
  const doc = { words: { relax: { word: "relax" } }, places: {} };
  const result = await fetchCards("abc-123", async (u) => { url = u; return respond(200, doc)(); });
  assert.equal(url, "/data/abc-123.cards.json");
  assert.deepEqual(result, { ...doc, figures: [] });
});

test("fetchCards returns null when the document does not exist yet", async () => {
  assert.equal(await fetchCards("x", respond(404, null)), null);
});

test("fetchCards returns null on network failure and unreadable JSON", async () => {
  assert.equal(await fetchCards("x", async () => { throw new Error("offline"); }), null);
  assert.equal(await fetchCards("x", async () => ({ ok: true, status: 200, json: async () => { throw new SyntaxError("bad"); } })), null);
});

test("fetchCards rejects documents with the wrong shape", async () => {
  assert.equal(await fetchCards("x", respond(200, [1, 2])), null);
  assert.equal(await fetchCards("x", respond(200, "text")), null);
  assert.deepEqual(await fetchCards("x", respond(200, { words: { a: {} } })), { words: { a: {} }, places: {}, figures: [] });
});

test("fetchCards encodes the passage id", async () => {
  let url = "";
  await fetchCards("a/b", async (u) => { url = u; return respond(404, null)(); });
  assert.equal(url, "/data/a%2Fb.cards.json");
});

test("fetchCards passes the passage figures through and ignores a malformed list", async () => {
  const figures = [{ afterParagraph: 1, imageUrl: "/data/x.figure-0-0a1b2c3d.jpg", imageAlt: "a park" }];
  assert.deepEqual((await fetchCards("x", respond(200, { words: {}, places: {}, figures }))).figures, figures);
  assert.deepEqual((await fetchCards("x", respond(200, { words: {}, places: {}, figures: "nope" }))).figures, []);
});
