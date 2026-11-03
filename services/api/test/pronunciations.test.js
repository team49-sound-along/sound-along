import assert from "node:assert/strict";
import { after, describe, test } from "node:test";
import { startLocalApp } from "./support/harness.js";

const ctx = await startLocalApp();
after(() => ctx.server.close());
const { call } = ctx;

describe("pronunciations", () => {
  test("starts empty; PUT creates (201) then replaces (200) and lowercases the word", async () => {
    assert.deepEqual((await call("GET", "/api/pronunciations")).json.data, []);
    const created = await call("PUT", "/api/pronunciations/Gaieties", { respelling: "gay-uh-teez" });
    assert.equal(created.status, 201);
    assert.equal(created.json.data.word, "gaieties");
    assert.ok(Date.parse(created.json.data.updatedAt));
    const replaced = await call("PUT", "/api/pronunciations/gaieties", { respelling: "/ɡˈAɪtˌiz/" });
    assert.equal(replaced.status, 200);
    assert.equal(replaced.json.data.respelling, "/ɡˈAɪtˌiz/");
  });

  test("GET is sorted by word", async () => {
    await call("PUT", "/api/pronunciations/don't", { respelling: "dohnt" });
    await call("PUT", "/api/pronunciations/anti-hero", { respelling: "an-tee hee-roh" });
    const words = (await call("GET", "/api/pronunciations")).json.data.map((p) => p.word);
    assert.deepEqual(words, ["anti-hero", "don't", "gaieties"]);
  });

  test("validates the word and the respelling", async () => {
    for (const word of ["two%20words", "caf%C3%A9", "x1", "a".repeat(41)]) {
      const r = await call("PUT", `/api/pronunciations/${word}`, { respelling: "ok" });
      assert.equal(r.status, 400, word);
      assert.match(r.json.error, /word/i);
    }
    const bad = ["", " ", "x".repeat(61), "gay_uh", "gay1", "//", "/a/b/", "/<b>/", "a/b", 5, undefined];
    for (const respelling of bad) {
      const r = await call("PUT", "/api/pronunciations/ok", { respelling });
      assert.equal(r.status, 400, String(respelling));
      assert.match(r.json.error, /respelling/i);
    }
    assert.equal((await call("PUT", "/api/pronunciations/ok", [])).status, 400);
    assert.equal((await call("PUT", "/api/pronunciations/ok", { respelling: "/a/" })).status, 201);
  });

  test("DELETE removes a fix, and an unknown word is a 404", async () => {
    const r = await call("DELETE", "/api/pronunciations/GAIETIES");
    assert.deepEqual(r.json.data, { word: "gaieties" });
    assert.equal((await call("DELETE", "/api/pronunciations/gaieties")).status, 404);
    assert.equal((await call("DELETE", "/api/pronunciations/bad%20word")).status, 400);
  });
});
