import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, readdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, describe, test } from "node:test";
import { GetObjectCommand, ListObjectsV2Command, PutObjectCommand } from "@aws-sdk/client-s3";
import { createS3Questions } from "../src/aws/s3Questions.js";
import { createAwsApp } from "../src/aws/awsApp.js";
import { createLocalQuestions } from "../src/questions/localQuestions.js";
import { resetReview } from "../src/questions/draft.js";
import { fakeClient, quiet, startLocalApp } from "./support/harness.js";

const ID = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98";
const NO_DRAFT_ID = "5af24980-4d6d-41c1-87fa-4f21cb2d169d";
const q = (n, extra = {}) => ({
  id: `q${n}`, skill: "literal", question: `Question ${n}?`, choices: ["One", "Two", "Three"], answerIndex: 1, evidenceSentence: n,
  evidenceQuote: "quote", checks: { answeredFromPassage: true, guessableWithoutPassage: n === 2 },
  review: { status: "approved", by: "someone" }, ...extra,
});
const draft = { version: 1, passageId: ID, title: "Park", status: "draft", generatedWith: { model: "m", promptVersion: "q2", date: "2026-11-03" }, questions: [q(1), q(2), q(3)] };

const dir = await mkdtemp(path.join(tmpdir(), "sa-q-"));
await writeFile(path.join(dir, `${ID}.timing.json`), JSON.stringify({ title: "Park", language: "en", words: [] }));
await writeFile(path.join(dir, `${ID}.mp3`), "x");
await mkdir(path.join(dir, "question-drafts"));
await writeFile(path.join(dir, "question-drafts", `${ID}.draft.json`), JSON.stringify(draft));
await writeFile(path.join(dir, "question-drafts", "notes.txt"), "ignored");
await writeFile(path.join(dir, "question-drafts", `${NO_DRAFT_ID}.draft.json`), "{not json"); // unreadable draft for a passage that does not exist
const ctx = await startLocalApp({ dir });
after(() => ctx.close());
const { call, base } = ctx;
const publish = (id, body) => call("POST", `/api/questions/drafts/${id}/publish`, body);
const item = (n, extra = {}) => ({ id: `q${n}`, question: `Question ${n}?`, choices: ["One", "Two", "Three"], ...extra });

describe("question draft routes (local)", () => {
  test("lists passages that have a usable draft, with counts and flagged questions", async () => {
    const r = await call("GET", "/api/questions/drafts");
    assert.equal(r.status, 200);
    assert.deepEqual(r.json.data, [{ passageId: ID, title: "Park", questionCount: 3, flaggedCount: 1, generatedOn: "2026-11-03", language: "en" }]);
  });

  test("a draft opens with every question pending, even if the file says approved", async () => {
    const r = await call("GET", `/api/questions/drafts/${ID}`);
    assert.equal(r.status, 200);
    assert.deepEqual(r.json.data.questions.map((x) => x.status), ["pending", "pending", "pending"]);
    assert.equal(r.json.data.questions[0].review, undefined);
    assert.equal(r.json.data.questions[0].evidenceQuote, "quote");
  });

  test("unknown, malformed or unreadable drafts are a plain 404", async () => {
    for (const id of ["nope", "..%2F..%2Fstate", NO_DRAFT_ID, "00000000-0000-0000-0000-000000000000"]) {
      assert.equal((await call("GET", `/api/questions/drafts/${id}`)).status, 404, id);
    }
  });

  test("a draft is never reachable through the data route", async () => {
    for (const p of [`/data/${ID}.draft.json`, `/data/question-drafts/${ID}.draft.json`, `/data/${ID}.questions.json`]) {
      assert.equal((await call("GET", p)).status, 404, p);
    }
  });

  test("publish rejects bad input and writes nothing", async () => {
    const bad = [{}, { approved: [] }, { approved: [item(1)], extra: true }, { approved: [item(9)] }, { approved: [item(1, { choices: ["a", "b"] })] }, { approved: [item(1), item(1)] }];
    for (const body of bad) assert.equal((await publish(ID, body)).status, 400, JSON.stringify(body));
    assert.equal((await publish(NO_DRAFT_ID, { approved: [item(1)] })).status, 404);
    assert.equal((await call("GET", `/data/${ID}.questions.json`)).status, 404);
    assert.ok(!(await readdir(dir)).some((f) => f.endsWith(".questions.json")));
  });

  test("publish writes only the approved questions, with the draft's answers, and students can then read them", async () => {
    const r = await publish(ID, { approved: [item(3), item(1, { question: "Edited question?" })] });
    assert.equal(r.status, 200);
    assert.equal(r.json.data.published, 2);
    const doc = JSON.parse(await readFile(path.join(dir, `${ID}.questions.json`), "utf8"));
    assert.equal(doc.reviewed, true);
    assert.match(doc.reviewedAt, /^\d{4}-\d{2}-\d{2}$/);
    assert.deepEqual(doc.questions.map((x) => [x.id, x.question, x.answerIndex, x.evidenceSentence]), [["q1", "Edited question?", 1, 1], ["q3", "Question 3?", 1, 3]]);
    const served = await call("GET", `/data/${ID}.questions.json`);
    assert.equal(served.status, 200);
    assert.equal(served.json.questions.length, 2);
    assert.ok(!served.text.includes("review\""));
    assert.ok(!served.text.includes("someone"));
  });

  test("a rejected question never appears and the draft file is left unchanged", async () => {
    const after = JSON.parse(await readFile(path.join(dir, "question-drafts", `${ID}.draft.json`), "utf8"));
    assert.deepEqual(after, draft);
  });

  test("publishing is rate limited like the other teacher changes", async () => {
    const limited = await startLocalApp({ dir, config: { writePerMinute: 1 } });
    try {
      assert.equal((await limited.call("POST", `/api/questions/drafts/${ID}/publish`, { approved: [item(1)] })).status, 200);
      assert.equal((await limited.call("POST", `/api/questions/drafts/${ID}/publish`, { approved: [item(1)] })).status, 429);
    } finally {
      limited.close();
    }
  });

  test("an oversized body is refused", async () => {
    const r = await publish(ID, { approved: [item(1, { question: "x".repeat(70_000) })] });
    assert.equal(r.status, 413);
  });
});

describe("local store", () => {
  test("missing folder lists nothing; ids come only from valid draft file names", async () => {
    const store = createLocalQuestions({ draftsDir: path.join(dir, "absent"), dataDir: dir });
    assert.deepEqual(await store.listDraftIds(), []);
    assert.deepEqual(await createLocalQuestions({ draftsDir: path.join(dir, "question-drafts"), dataDir: dir }).listDraftIds().then((x) => x.sort()), [ID, NO_DRAFT_ID].sort());
  });
  test("the seed shape (review reset) loads as an unreviewed draft", async () => {
    const reset = resetReview(draft);
    assert.ok(reset.questions.every((x) => x.review === undefined));
  });
});

describe("S3 store", () => {
  test("lists draft ids under raw/questions only, across pages", async () => {
    const client = fakeClient((c, n) => (n === 1
      ? { Contents: [{ Key: `raw/questions/${ID}.draft.json` }, { Key: "raw/questions/readme.txt" }], IsTruncated: true, NextContinuationToken: "t" }
      : { Contents: [{ Key: `raw/questions/${NO_DRAFT_ID}.draft.json` }] }));
    assert.deepEqual(await createS3Questions({ s3: client, bucket: "B" }).listDraftIds(), [ID, NO_DRAFT_ID]);
    assert.equal(client.calls[0].name, "ListObjectsV2Command");
    assert.equal(client.calls[0].input.Prefix, "raw/questions/");
    assert.equal(client.calls[1].input.ContinuationToken, "t");
  });
  test("reads a draft from raw/questions and treats a missing or broken one as absent", async () => {
    const body = (text) => ({ Body: { transformToString: async () => text } });
    const store = createS3Questions({ s3: fakeClient(() => body(JSON.stringify(draft))), bucket: "B" });
    assert.equal((await store.readDraft(ID)).passageId, ID);
    assert.equal(await createS3Questions({ s3: fakeClient(() => body("{")), bucket: "B" }).readDraft(ID), null);
    const missing = fakeClient(() => { throw Object.assign(new Error("x"), { name: "NoSuchKey" }); });
    assert.equal(await createS3Questions({ s3: missing, bucket: "B" }).readDraft(ID), null);
    assert.equal(await createS3Questions({ s3: missing, bucket: "B" }).readDraft("../x"), null);
    assert.equal(missing.calls.length, 1);
    const boom = fakeClient(() => { throw new Error("denied"); });
    await assert.rejects(createS3Questions({ s3: boom, bucket: "B" }).readDraft(ID), /denied/);
  });
  test("publish writes data/<id>.questions.json with revalidating cache headers and never touches raw/", async () => {
    const client = fakeClient();
    await createS3Questions({ s3: client, bucket: "B" }).publish(ID, { reviewed: true, questions: [] });
    const [call] = client.calls;
    assert.equal(call.name, "PutObjectCommand");
    assert.equal(call.input.Key, `data/${ID}.questions.json`);
    assert.equal(call.input.CacheControl, "public, max-age=0, must-revalidate");
    assert.equal(call.input.ContentType, "application/json");
    assert.deepEqual(JSON.parse(call.input.Body), { reviewed: true, questions: [] });
    await assert.rejects(createS3Questions({ s3: client, bucket: "B" }).publish("../evil", {}));
  });
});

describe("AWS app wiring", () => {
  test("the review routes run against S3 and publish writes only the approved file", async () => {
    const ready = [{ id: ID, title: "Park", language: "en", createdAt: new Date().toISOString(), pairId: null, translationOf: null, series: null }];
    const s3 = fakeClient((c) => {
      if (c instanceof ListObjectsV2Command) return { Contents: [{ Key: `raw/questions/${ID}.draft.json` }] };
      if (c instanceof GetObjectCommand) return { Body: { transformToString: async () => JSON.stringify(draft) } };
      return {};
    });
    const ddb = fakeClient((c) => ({ Items: ready.map((p) => ({ pk: "PASSAGE", sk: p.id, ...p })) }));
    const app = createAwsApp({ BUCKET: "B", TABLE_NAME: "T" }, { ddb, s3, sfn: fakeClient() }, quiet);
    const server = await new Promise((resolve) => { const s = app.listen(0, "127.0.0.1", () => resolve(s)); });
    try {
      const url = `http://127.0.0.1:${server.address().port}/api/questions/drafts`;
      const list = await (await fetch(url)).json();
      assert.equal(list.data.length, 1, JSON.stringify(list));
      const res = await fetch(`${url}/${ID}/publish`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ approved: [item(2)] }) });
      assert.equal(res.status, 200);
      const puts = s3.calls.filter((c) => c.name === "PutObjectCommand");
      assert.deepEqual(puts.map((c) => c.input.Key), [`data/${ID}.questions.json`]);
    } finally {
      server.closeAllConnections?.();
      server.close();
    }
  });
});
