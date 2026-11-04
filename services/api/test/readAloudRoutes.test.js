import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, before, describe, test } from "node:test";
import { startLocalApp } from "./support/harness.js";

const PID = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98";
const WORDS = ["The", "island", "was", "quiet", "because", "nobody", "lived", "there", "anymore", "really"];
const timing = {
  id: PID, title: "Island", engine: "kokoro", voice: "af_heart", language: "en", duration_ms: 60000, vocab: {},
  metrics: { characters: 100, words: WORDS.length, audioSeconds: 6, generateSeconds: 1, unalignedWords: 0 },
  words: WORDS.map((text, i) => ({ i, text: i === 3 ? `${text}.` : text, start_ms: i * 100, end_ms: i * 100 + 90, sentence: 0, paragraph: 0, aligned: true })),
};
const CLASS = "cls-g3-p2";
const result = (over = {}) => ({ passageId: PID, classId: CLASS, language: "en", wordsTotal: 10, wordsRead: 6, finished: false, retried: 0, words: [{ i: 4, kind: "skipped" }, { i: 1, kind: "differs" }], ...over });

let app;
before(async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "sa-ra-api-"));
  await writeFile(path.join(dir, `${PID}.timing.json`), JSON.stringify(timing));
  await writeFile(path.join(dir, `${PID}.mp3`), "x");
  app = await startLocalApp({ dir, config: { writePerMinute: 1000 } });
});
after(() => app.close());

const post = (body) => app.call("POST", "/api/read-aloud/results", body);
const insights = (q = "") => app.call("GET", `/api/insights/read-aloud${q}`);

describe("read-aloud results and the teacher view", () => {
  test("nothing to show before any session", async () => {
    const { json } = await insights(`?passageId=${PID}`);
    assert.equal(json.data.words.state, "none");
    assert.equal(json.data.totals.sessions, 0);
  });

  test("bad payloads are rejected with 400 and nothing is stored", async () => {
    for (const bad of [result({ transcript: "hello" }), result({ words: [{ i: 99, kind: "skipped" }] }), result({ readerCode: "ann lee" }), "x"]) assert.equal((await post(bad)).status, 400);
    assert.equal((await insights()).json.data.totals.sessions, 0);
  });

  test("under the minimum no word and no number is shown, then three sessions show the word from the server's own text", async () => {
    await post(result());
    await post(result());
    const small = (await insights(`?passageId=${PID}`)).json;
    assert.equal(small.data.words.state, "small");
    assert.equal(small.data.hiddenSessions, 2);
    assert.equal(JSON.stringify(small).includes("because"), false);
    await post(result({ wordsRead: 10, finished: true, words: [] }));
    const { data } = (await insights(`?passageId=${PID}`)).json;
    assert.equal(data.words.state, "ok");
    assert.deepEqual(data.words.items.map((w) => [w.word, w.missed, w.sessions]), [["because", 2, 3], ["island", 2, 3]]);
    assert.equal(data.totals.finishRate, 1 / 3);
    assert.ok(data.steps.some((s) => s.includes('"because"')));
    assert.equal(data.weeks.length, 8);
    assert.equal(data.weeks.at(-1).sessions, 3);
    assert.equal(data.classes.find((c) => c.id === CLASS).enough, true);
    assert.equal(data.classes.find((c) => c.id === "cls-g4-p4").enough, false);
  });

  test("the organisation view (no passage chosen) ranks words across passages", async () => {
    const { data } = (await insights()).json;
    assert.equal(data.words.items[0].word, "because");
  });

  test("filters are validated", async () => {
    assert.equal((await insights("?passageId=nope")).status, 400);
    assert.equal((await insights("?classId=nope")).status, 400);
    assert.equal((await insights(`?classId=${CLASS}&passageId=${PID}`)).status, 200);
  });

  test("with sharing off for the class nothing is kept, and the switch is per class", async () => {
    const before = (await insights()).json.data.totals.sessions;
    assert.equal((await app.call("PUT", "/api/read-aloud/settings", { classId: "cls-g4-p4", share: false })).status, 200);
    assert.equal((await post(result({ classId: "cls-g4-p4" }))).json.data.recorded, false);
    assert.equal((await insights()).json.data.totals.sessions, before);
    assert.equal((await post(result())).json.data.recorded, true); // another class is unaffected
    await app.call("PUT", "/api/read-aloud/settings", { share: false }); // school default off: a result with no class is dropped too
    assert.equal((await post(result({ classId: undefined }))).json.data.recorded, false);
    await app.call("PUT", "/api/read-aloud/settings", { share: true });
    await app.call("PUT", "/api/read-aloud/settings", { classId: "cls-g4-p4", share: true });
  });

  test("settings: defaults on, readers off; strict patches", async () => {
    const { data } = (await app.call("GET", "/api/read-aloud/settings")).json;
    assert.deepEqual(data.defaults, { mic: true, share: true, readers: false });
    assert.equal(data.classes.length, 4);
    for (const bad of [{}, { mic: "yes" }, { classId: "nope", mic: false }, { name: "x", mic: false }]) assert.equal((await app.call("PUT", "/api/read-aloud/settings", bad)).status, 400);
  });

  test("reader codes: dropped and refused while the switch is off, kept and shown only when it is on", async () => {
    const CODE = "K7Q29XMA";
    await post(result({ readerCode: CODE })); // switch off: the code is not kept
    assert.equal((await app.call("GET", `/api/insights/read-aloud/readers?classId=${CLASS}`)).status, 404);
    await app.call("PUT", "/api/read-aloud/settings", { classId: CLASS, readers: true });
    assert.equal((await app.call("GET", `/api/insights/read-aloud/readers?classId=${CLASS}`)).json.data.readers.length, 0);
    await post(result({ readerCode: CODE, wordsRead: 5 }));
    await post(result({ readerCode: CODE, wordsRead: 8 }));
    const list = (await app.call("GET", `/api/insights/read-aloud/readers?classId=${CLASS}`)).json.data;
    assert.deepEqual(list.readers, [{ code: CODE, sessions: 2, passages: 1 }]);
    const one = (await app.call("GET", `/api/insights/read-aloud/readers?classId=${CLASS}&code=${CODE}`)).json.data.selected;
    assert.deepEqual(one.sessions.map((s) => s.pct), [50, 80]);
    assert.deepEqual(one.words.map((w) => w.word), ["because", "island"]);
    assert.ok(one.summary.length > 0);
    assert.equal((await app.call("GET", `/api/insights/read-aloud/readers?classId=${CLASS}&code=bad code`)).status, 400);
    assert.equal((await app.call("GET", "/api/insights/read-aloud/readers")).status, 400);
    await app.call("PUT", "/api/read-aloud/settings", { classId: CLASS, readers: false }); // turned off: nothing is shown any more
    assert.equal((await app.call("GET", `/api/insights/read-aloud/readers?classId=${CLASS}&code=${CODE}`)).status, 404);
    await post(result({ readerCode: "ZZZZ2222" }));
    await app.call("PUT", "/api/read-aloud/settings", { classId: CLASS, readers: true });
    assert.equal((await app.call("GET", `/api/insights/read-aloud/readers?classId=${CLASS}`)).json.data.readers.some((r) => r.code === "ZZZZ2222"), false);
  });

  test("readers need sharing: with sharing off the switch is not in force", async () => {
    await app.call("PUT", "/api/read-aloud/settings", { classId: CLASS, share: false });
    assert.equal((await app.call("GET", `/api/insights/read-aloud/readers?classId=${CLASS}`)).status, 404);
    await app.call("PUT", "/api/read-aloud/settings", { classId: CLASS, share: true });
  });
});
