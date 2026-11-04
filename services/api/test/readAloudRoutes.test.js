import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
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
  app = await startLocalApp({ dir, config: { writePerMinute: 1000, readerInsights: true } });
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

  test("the passage text is returned with per-word counts only once the group passes the minimum", async () => {
    const before = (await insights(`?passageId=${PID}`)).json.data;
    assert.equal(before.passage, null);
    assert.equal((await insights()).json.data.passage, null); // no passage chosen: no passage text
  });

  test("under the minimum no word and no number is shown, then three sessions show the word from the server's own text", async () => {
    await post(result());
    await post(result());
    const small = (await insights(`?passageId=${PID}`)).json;
    assert.equal(small.data.words.state, "small");
    assert.equal(small.data.hiddenSessions, 2);
    assert.equal(small.data.passage, null);
    assert.equal(JSON.stringify(small).includes("because"), false);
    await post(result({ wordsRead: 10, finished: true, words: [] }));
    const { data } = (await insights(`?passageId=${PID}`)).json;
    assert.equal(data.words.state, "ok");
    assert.deepEqual(data.words.items.map((w) => [w.word, w.missed, w.sessions]), [["because", 2, 3], ["island", 2, 3]]);
    assert.equal(data.totals.finishRate, 1 / 3);
    assert.ok(data.steps.some((s) => s.includes('"because"')));
    assert.equal(data.passage.sessions, 3);
    assert.deepEqual(data.passage.tokens.map((t) => [t.text, t.missed]), WORDS.map((w, i) => [i === 3 ? `${w}.` : w, i === 1 || i === 4 ? 2 : 0]));
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

  const readersOf = (q) => app.call("GET", `/api/insights/read-aloud/readers${q}`);
  const CODE = "K7Q29XMA";

  test("reader codes: dropped and an empty view while the switch is off, kept and shown only when it is on", async () => {
    await post(result({ readerCode: CODE })); // switch off: the code is not kept
    const off = await readersOf(`?classId=${CLASS}`);
    assert.equal(off.status, 200);
    assert.deepEqual(off.json.data, { classId: CLASS, enabled: false, enough: false, readers: [], progress: [], selected: null });
    await app.call("PUT", "/api/read-aloud/settings", { classId: CLASS, readers: true });
    const none = (await readersOf(`?classId=${CLASS}`)).json.data;
    assert.deepEqual([none.enabled, none.enough, none.readers.length], [true, false, 0]);
    await post(result({ readerCode: CODE, wordsRead: 5 }));
    await post(result({ readerCode: CODE, wordsRead: 8 }));
    await post(result({ readerCode: CODE, wordsRead: 9 }));
    await post(result({ readerCode: "ZZZZ2222" }));
    const few = (await readersOf(`?classId=${CLASS}&code=${CODE}`)).json.data; // two readers: below the minimum, nothing listed
    assert.deepEqual([few.enough, few.readers, few.selected], [false, [], null]);
    await post(result({ readerCode: "MMMM3333" }));
    const list = (await readersOf(`?classId=${CLASS}`)).json.data;
    assert.deepEqual(list.readers.map((r) => [r.code, r.sessions]), [["K7Q29XMA", 3], ["MMMM3333", 1], ["ZZZZ2222", 1]]); // alphabetical, not by result
    assert.deepEqual(list.progress, [{ code: "K7Q29XMA", pcts: [50, 80, 90] }, { code: "MMMM3333", pcts: [60] }, { code: "ZZZZ2222", pcts: [60] }]);
    const one = (await readersOf(`?classId=${CLASS}&code=${CODE}`)).json.data.selected;
    assert.deepEqual(one.sessions.map((s) => s.pct), [50, 80, 90]);
    assert.deepEqual(one.words.map((w) => w.word), ["because", "island"]);
    assert.ok(one.summary.length > 0);
    assert.equal((await readersOf(`?classId=${CLASS}&code=K7Q29XMB`)).json.data.selected, null); // not a code in this class
    await app.call("PUT", "/api/read-aloud/settings", { classId: CLASS, readers: false }); // turned off: nothing is shown any more
    const gone = (await readersOf(`?classId=${CLASS}&code=${CODE}`)).json.data;
    assert.deepEqual([gone.enabled, gone.readers, gone.selected], [false, [], null]);
    assert.ok(!JSON.stringify(gone).includes(CODE));
  });

  test("padding with one reader code never unlocks a word list; three distinct codes do", async () => {
    const C2 = "cls-g5-ell";
    await app.call("PUT", "/api/read-aloud/settings", { classId: C2, readers: true });
    for (let n = 0; n < 5; n += 1) await post(result({ classId: C2, readerCode: "PADD2222" }));
    const padded = (await insights(`?passageId=${PID}&classId=${C2}`)).json.data;
    assert.equal(padded.words.state, "small");
    assert.equal(padded.totals.sessions, 0);
    assert.equal(JSON.stringify(padded).includes("because"), false);
    for (let n = 0; n < 5; n += 1) await post(result({ classId: C2 })); // sessions without a code do not count while the class uses codes
    assert.equal((await insights(`?passageId=${PID}&classId=${C2}`)).json.data.words.state, "small");
    await post(result({ classId: C2, readerCode: "PADE2222" }));
    assert.equal((await insights(`?passageId=${PID}&classId=${C2}`)).json.data.words.state, "small");
    await post(result({ classId: C2, readerCode: "PADF2222" }));
    const open = (await insights(`?passageId=${PID}&classId=${C2}`)).json.data;
    assert.equal(open.words.state, "ok");
    await app.call("PUT", "/api/read-aloud/settings", { classId: C2, readers: false });
  });

  test("the readers route refuses unknown classes, a missing class and bad codes, and never leaks across classes", async () => {
    assert.equal((await readersOf("?classId=nope")).status, 400);
    assert.equal((await readersOf("")).status, 400);
    assert.equal((await readersOf(`?classId=${CLASS}&code=bad code`)).status, 400);
    await app.call("PUT", "/api/read-aloud/settings", { classId: "cls-g4-p4", readers: true });
    assert.deepEqual((await readersOf("?classId=cls-g4-p4")).json.data.readers, []);
    await app.call("PUT", "/api/read-aloud/settings", { classId: "cls-g4-p4", readers: false });
  });

  test("readers need sharing: with sharing off the switch is not in force", async () => {
    await app.call("PUT", "/api/read-aloud/settings", { classId: CLASS, readers: true });
    await app.call("PUT", "/api/read-aloud/settings", { classId: CLASS, share: false });
    assert.equal((await readersOf(`?classId=${CLASS}`)).json.data.enabled, false);
    await app.call("PUT", "/api/read-aloud/settings", { classId: CLASS, share: true });
    await app.call("PUT", "/api/read-aloud/settings", { classId: CLASS, readers: false });
  });

  test("settings PUT rejects unknown fields, unknown classes and wrong types, and changes nothing", async () => {
    const before = JSON.stringify((await app.call("GET", "/api/read-aloud/settings")).json);
    for (const bad of [{ mic: false, extra: 1 }, { classId: "nope", mic: false }, { classId: 5, mic: false }, { mic: 1 }, { readers: "yes" }, []]) {
      assert.equal((await app.call("PUT", "/api/read-aloud/settings", bad)).status, 400, JSON.stringify(bad));
    }
    assert.equal(JSON.stringify((await app.call("GET", "/api/read-aloud/settings")).json), before);
  });
});

describe("READER_INSIGHTS flag off (the deployed default)", () => {
  test("codes are dropped, the readers route is a 404 and the settings never say readers are on", async () => {
    const dir = await mkdtemp(path.join(tmpdir(), "sa-ra-flag-"));
    await writeFile(path.join(dir, `${PID}.timing.json`), JSON.stringify(timing));
    await writeFile(path.join(dir, `${PID}.mp3`), "x");
    const off = await startLocalApp({ dir, config: { writePerMinute: 1000 } }); // no readerInsights in the config
    try {
      assert.equal((await off.call("PUT", "/api/read-aloud/settings", { classId: CLASS, readers: true })).status, 200);
      const view = (await off.call("GET", "/api/read-aloud/settings")).json.data;
      assert.equal(view.readersAvailable, false);
      assert.equal(view.classes.find((c) => c.id === CLASS).readers, false);
      for (let n = 0; n < 4; n += 1) assert.equal((await off.call("POST", "/api/read-aloud/results", result({ readerCode: "K7Q29XMA" }))).json.data.recorded, true);
      assert.equal((await off.call("GET", `/api/insights/read-aloud/readers?classId=${CLASS}`)).status, 404);
      assert.ok(!(await readFile(path.join(dir, "state.json"), "utf8")).includes("K7Q29XMA")); // never written
      const counted = (await off.call("GET", "/api/insights/read-aloud")).json.data;
      assert.equal(counted.totals.sessions, 4); // sessions are still counted without codes
    } finally {
      off.close();
    }
  });
});

describe("rate limits", () => {
  test("the teacher reads and the settings writes are limited like the rest of the API", async () => {
    const dir = await mkdtemp(path.join(tmpdir(), "sa-ra-lim-"));
    await writeFile(path.join(dir, `${PID}.timing.json`), JSON.stringify(timing));
    await writeFile(path.join(dir, `${PID}.mp3`), "x");
    const limited = await startLocalApp({ dir, config: { writePerMinute: 2, readPerMinute: 3 } });
    try {
      const reads = [];
      for (let n = 0; n < 4; n += 1) reads.push((await limited.call("GET", "/api/insights/read-aloud")).status);
      assert.deepEqual(reads, [200, 200, 200, 429]);
      const writes = [];
      for (let n = 0; n < 3; n += 1) writes.push((await limited.call("PUT", "/api/read-aloud/settings", { mic: true })).status);
      assert.deepEqual(writes, [200, 200, 429]);
      assert.equal((await limited.call("POST", "/api/read-aloud/results", result())).status, 429); // results share the write limiter
    } finally {
      limited.close();
    }
  });
});
