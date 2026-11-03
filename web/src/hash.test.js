import { test } from "node:test";
import assert from "node:assert/strict";
import { sha256Hex } from "./hash.js";

test("matches the known SHA-256 of the empty string and of 'abc'", async () => {
  assert.equal(await sha256Hex(""), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  assert.equal(await sha256Hex("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
});

test("hashes the UTF-8 bytes, so non-ASCII text is stable", async () => {
  assert.equal((await sha256Hex("En español: visitar")).length, 64);
});
