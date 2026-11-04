import assert from "node:assert/strict";
import { test } from "node:test";
import express from "express";
import { MAX_DRAFTS_PER_LIST, questionRoutes } from "../src/routes/questions.js";

const idOf = (n) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const draftFor = (id) => ({
  version: 1, passageId: id, title: `T ${id.slice(-4)}`, status: "draft", generatedWith: { model: "m", promptVersion: "q2", date: "2026-11-03" },
  questions: [{ id: "q1", skill: "literal", question: "Q?", choices: ["a", "b", "c"], answerIndex: 1, evidenceSentence: 0, evidenceQuote: "x", checks: {} }],
});

async function list(ids, { throwFor = new Set(), logger } = {}) {
  const reads = [];
  const questions = {
    listDraftIds: async () => ids,
    readDraft: async (id) => {
      reads.push(id);
      if (throwFor.has(id)) throw new Error("SECRET-TOKEN boom");
      return draftFor(id);
    },
    publish: async () => {},
  };
  const api = express();
  questionRoutes(api, { questions, readyList: async () => ids.map((id) => ({ id, language: "en" })), writeLimiter: () => true, logger });
  const server = await new Promise((r) => { const s = api.listen(0, "127.0.0.1", () => r(s)); });
  try {
    const res = await fetch(`http://127.0.0.1:${server.address().port}/questions/drafts`);
    return { status: res.status, json: await res.json(), reads };
  } finally {
    server.closeAllConnections?.();
    server.close();
  }
}

test("one unreadable draft is skipped and logged with its passage id only", async () => {
  const ids = [idOf(1), idOf(2), idOf(3)];
  const logged = [];
  const r = await list(ids, { throwFor: new Set([idOf(2)]), logger: { error: (...a) => logged.push(a), warn() {}, info() {} } });
  assert.equal(r.status, 200);
  assert.deepEqual(r.json.data.map((d) => d.passageId).sort(), [idOf(1), idOf(3)]);
  assert.equal(r.json.meta.more, false);
  assert.equal(logged.length, 1);
  assert.equal(logged[0][1].passageId, idOf(2));
});

test("a big library is capped per request and says there is more", async () => {
  const ids = Array.from({ length: MAX_DRAFTS_PER_LIST + 25 }, (_, i) => idOf(i + 1));
  const r = await list(ids, { logger: { error() {}, warn() {}, info() {} } });
  assert.equal(r.reads.length, MAX_DRAFTS_PER_LIST);
  assert.equal(r.json.data.length, MAX_DRAFTS_PER_LIST);
  assert.deepEqual(r.json.meta, { more: true, limit: MAX_DRAFTS_PER_LIST, total: MAX_DRAFTS_PER_LIST + 25 });
});
