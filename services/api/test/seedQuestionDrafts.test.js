import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import { seedQuestionDrafts } from "../scripts/seedQuestionDrafts.js";

const ID = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98";
const quiet = { info() {}, warn() {} };
const sample = { version: 1, passageId: ID, title: "Park", status: "approved", reviewed: true, questions: [{ id: "q1", review: { status: "approved", by: "x" }, status: "approved" }] };

test("copies drafts with every review field reset and leaves the source alone", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "sa-seed-"));
  const from = path.join(root, "samples");
  const to = path.join(root, "data", "question-drafts");
  await mkdir(from);
  await writeFile(path.join(from, `${ID}.draft.json`), JSON.stringify(sample));
  await writeFile(path.join(from, "notes.md"), "skip me");
  await writeFile(path.join(from, "bad.draft.json"), "{");
  const result = await seedQuestionDrafts({ from, to, logger: quiet });
  assert.deepEqual(result.copied, [ID]);
  assert.deepEqual(await readdir(to), [`${ID}.draft.json`]);
  const out = JSON.parse(await readFile(path.join(to, `${ID}.draft.json`), "utf8"));
  assert.equal(out.status, "draft");
  assert.equal(out.reviewed, undefined);
  assert.equal(out.questions[0].review, undefined);
  assert.equal(out.questions[0].status, undefined);
  assert.deepEqual(JSON.parse(await readFile(path.join(from, `${ID}.draft.json`), "utf8")), sample);
});

test("refuses to write into the source folder", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "sa-seed-"));
  await assert.rejects(seedQuestionDrafts({ from: root, to: root, logger: quiet }), /different folder/);
  await assert.rejects(seedQuestionDrafts({ from: root, to: path.join(root, "inside"), logger: quiet }), /different folder/);
});

test("a missing source folder is a clear error", async () => {
  await assert.rejects(seedQuestionDrafts({ from: "/nonexistent-sa-dir", to: path.join(tmpdir(), "sa-x"), logger: quiet }), /not found/);
});
