import { test } from "node:test";
import assert from "node:assert/strict";
import { createReadAlong, cursorIndex, editDistance, feed, normalizeWord, restartFrom, similarity, summarize } from "./readAloud.js";

test("restartFrom with no spoken words does not throw and keeps a sensible state", () => {
  const empty = createReadAlong([], { language: "en" });
  const next = restartFrom(empty, 3);
  assert.equal(next.cursor, 0);
  assert.deepEqual(next.read, {});
  assert.equal(next.targets.length, 0);
  assert.equal(next.retries, empty.retries);
  assert.doesNotThrow(() => restartFrom(empty, 0, { retry: false }));
});

const words = (text) =>text.split(/\s+/).map((t, i) => ({ i, text: t }));

/** Feed scripted results [id, transcript, isFinal] and collect every event. */
function run(text, script, language = "en", start) {
  let state = start ?? createReadAlong(words(text), { language });
  const events = [];
  for (const [id, transcript, isFinal = true] of script) {
    const out = feed(state, { id, transcript, isFinal });
    state = out.state;
    events.push(...out.events);
  }
  return { state, events };
}
const types = (events) => events.map((e) => e.type);
const only = (events, type) => events.filter((e) => e.type === type);

test("normalizeWord folds case, punctuation and accents", () => {
  assert.equal(normalizeWord("Don’t!", "en"), "dont");
  assert.equal(normalizeWord("“Hello,”", "en"), "hello");
  assert.equal(normalizeWord("café", "en"), "cafe");
  assert.equal(normalizeWord("está", "es"), "esta");
  assert.equal(normalizeWord("¿Qué?", "es"), "que");
});

test("Spanish keeps the n with tilde, because ano and año are different words", () => {
  assert.notEqual(normalizeWord("año", "es"), normalizeWord("ano", "es"));
});

test("edit distance and similarity", () => {
  assert.equal(editDistance("kitten", "sitting"), 3);
  assert.equal(similarity("because", "because"), 1);
  assert.ok(similarity("because", "becuase") > 0.7);
  assert.ok(similarity("cat", "dog") < 0.2);
});

test("exact read: every word advances in order, then done", () => {
  const { events, state } = run("The dog ran to the big red barn.", [[0, "the dog ran to the big red barn", true]]);
  assert.deepEqual(only(events, "advance").map((e) => e.index), [0, 1, 2, 3, 4, 5, 6, 7]);
  assert.equal(types(events).at(-1), "done");
  assert.equal(only(events, "done").length, 1);
  assert.equal(summarize(state).read, 8);
  assert.equal(cursorIndex(state), null);
});

test("progressive interim results advance without duplicates", () => {
  const { events } = run("The dog ran to the barn", [
    [0, "the", false], [0, "the dog", false], [0, "the dog ran to", false], [0, "the dog ran to the barn", false], [0, "the dog ran to the barn", true],
  ]);
  assert.deepEqual(only(events, "advance").map((e) => e.index), [0, 1, 2, 3, 4, 5]);
  assert.equal(only(events, "done").length, 1);
  assert.equal(only(events, "skipped").length, 0);
});

test("a skipped word is detected when the next words are heard", () => {
  const { events, state } = run("I like it because it is fun", [[0, "I like it it is fun"]]);
  const skipped = only(events, "skipped");
  assert.equal(skipped.length, 1);
  assert.equal(skipped[0].index, 3);
  assert.deepEqual(skipped[0].indexes, [3]);
  assert.equal(skipped[0].word, "because");
  assert.deepEqual(only(events, "advance").map((e) => e.index), [0, 1, 2]);
  assert.equal(state.halted.type, "skipped");
});

test("several skipped words are reported together", () => {
  const { events } = run("we went to the big park today", [[0, "we went to park today"]]);
  const skipped = only(events, "skipped");
  assert.equal(skipped.length, 1);
  assert.deepEqual(skipped[0].indexes, [3, 4]);
  assert.equal(skipped[0].index, 3);
});

test("a skipped word is found across separate results", () => {
  const { events } = run("I like it because it is fun", [[0, "I like it"], [1, "it is fun"]]);
  assert.equal(only(events, "skipped")[0].index, 3);
});

test("a repeated word is not an error", () => {
  const { events } = run("the dog ran fast", [[0, "the the dog dog ran fast"]]);
  assert.deepEqual(types(events), ["advance", "advance", "advance", "advance", "done"]);
});

test("re-reading the start of a sentence is tolerated", () => {
  const { events } = run("the dog ran fast", [[0, "the dog the dog ran fast"]]);
  assert.equal(only(events, "skipped").length + only(events, "differs").length, 0);
  assert.equal(types(events).at(-1), "done");
});

test("filler words are ignored", () => {
  const { events } = run("the dog ran fast", [[0, "um the uh dog hmm ran er fast"]]);
  assert.deepEqual(types(events), ["advance", "advance", "advance", "advance", "done"]);
});

test("a clearly different word followed by the right text is reported as heard differently", () => {
  const { events, state } = run("the cat sat on the mat", [[0, "the cat sit on the mat"]]);
  const differs = only(events, "differs");
  assert.equal(differs.length, 1);
  assert.equal(differs[0].index, 2);
  assert.equal(differs[0].heard, "sit");
  assert.equal(differs[0].expected, "sat");
  assert.equal(state.halted.type, "differs");
});

test("close pronunciations and recognizer spelling noise are accepted", () => {
  const { events } = run("because everyone wanted breakfast", [[0, "becuase everyone wanted breakfas"]]);
  assert.equal(only(events, "differs").length + only(events, "skipped").length, 0);
  assert.equal(types(events).at(-1), "done");
});

test("a noisy unrelated word does not stop the reader", () => {
  const { events } = run("the dog ran fast", [[0, "the dog banana ran fast"]]);
  assert.equal(only(events, "skipped").length + only(events, "differs").length, 0);
  assert.equal(types(events).at(-1), "done");
});

test("Spanish accents do not matter, and a missing n tilde is close enough only where safe", () => {
  const { events } = run("El niño está cansado", [[0, "el nino esta cansado"]], "es");
  assert.equal(only(events, "differs").length + only(events, "skipped").length, 0);
  assert.equal(types(events).at(-1), "done");
});

test("Spanish skipped word", () => {
  const { events } = run("Mi hermana pequeña juega en el jardín", [[0, "mi hermana juega en el jardin"]], "es");
  assert.equal(only(events, "skipped")[0].word, "pequeña");
});

test("numbers match as digits or words in both directions", () => {
  assert.equal(types(run("I have 3 cats", [[0, "i have three cats"]]).events).at(-1), "done");
  assert.equal(types(run("I have three cats", [[0, "i have 3 cats"]]).events).at(-1), "done");
  assert.equal(types(run("There are 21 pupils", [[0, "there are twenty one pupils"]]).events).at(-1), "done");
  assert.equal(types(run("Tengo 5 gatos", [[0, "tengo cinco gatos"]], "es").events).at(-1), "done");
});

test("a year or large number the app cannot spell is accepted rather than flagged", () => {
  assert.equal(types(run("It was 1998 then", [[0, "it was nineteen ninety eight then"]]).events).includes("skipped"), false);
});

test("words split or joined by the recognizer still match", () => {
  assert.equal(types(run("everyone smiled", [[0, "every one smiled"]]).events).at(-1), "done");
  assert.equal(types(run("every one smiled", [[0, "everyone smiled"]]).events).at(-1), "done");
  assert.equal(types(run("a well-known story", [[0, "a well known story"]]).events).at(-1), "done");
});

test("punctuation-only tokens are not expected to be spoken", () => {
  const { events } = run("Wait — what", [[0, "wait what"]]);
  assert.deepEqual(only(events, "advance").map((e) => e.index), [0, 2]);
  assert.equal(types(events).at(-1), "done");
});

test("recognizer restart mid-sentence keeps the place", () => {
  const first = run("the dog ran to the big barn", [[0, "the dog ran", true]]);
  const second = run("", [[10000, "to the big barn", true]], "en", first.state);
  assert.equal(types(second.events).at(-1), "done");
  assert.equal(summarize(second.state).read, 7);
});

test("restart while the old interim is unfinished does not repeat or lose words", () => {
  const first = run("the dog ran to the big barn", [[0, "the dog ran", false]]);
  const flushed = run("", [[0, "the dog ran", true]], "en", first.state);
  const second = run("", [[10000, "to the big barn", true]], "en", flushed.state);
  assert.equal(types(second.events).at(-1), "done");
});

test("interim results never cause a false skip", () => {
  const { events } = run("I like it because it is fun", [[0, "I like it it", false]]);
  assert.equal(only(events, "skipped").length, 0);
  assert.deepEqual(only(events, "advance").map((e) => e.index), [0, 1, 2]);
});

test("an interim guess that is revised later is not held against the reader", () => {
  const { events } = run("I like it because it is fun", [[0, "I like it be", false], [0, "I like it because it", false], [0, "I like it because it is fun", true]]);
  assert.equal(only(events, "skipped").length + only(events, "differs").length, 0);
  assert.equal(types(events).at(-1), "done");
});

test("an interim result with enough words after a gap does report a skip", () => {
  const { events } = run("I like it because it is very fun today", [[0, "I like it it is very fun", false]]);
  assert.equal(only(events, "skipped")[0].index, 3);
});

test("a mispronounced word followed by a pause is flagged as heard differently, not skipped", () => {
  const { events } = run("I like it because it is fun", [[0, "I like it becoz", true], [1, "it is fun", true]]);
  assert.equal(only(events, "skipped").length, 0);
  assert.equal(only(events, "differs")[0].index, 3);
  assert.equal(only(events, "differs")[0].heard, "becoz");
});

test("after a stop, results are ignored until the reader restarts from a word", () => {
  const first = run("I like it because it is fun", [[0, "I like it it is fun"]]);
  const ignored = run("", [[1, "because it is fun"]], "en", first.state);
  assert.deepEqual(ignored.events, []);
  const restarted = restartFrom(ignored.state, 0);
  assert.equal(cursorIndex(restarted), 0);
  const again = run("", [[2, "I like it because it is fun"]], "en", restarted);
  assert.equal(types(again.events).at(-1), "done");
  const s = summarize(again.state);
  assert.equal(s.read, 7);
  assert.equal(s.retried, 1);
  assert.equal(s.skipped, 1);
});

test("old results of a still-running segment are not replayed after a restart", () => {
  const first = run("one two three four five six seven", [[0, "one two four five six seven", false]]);
  assert.equal(first.state.halted.index, 2);
  const restarted = restartFrom(first.state, 2);
  const next = run("", [[0, "one two four five six seven three four five six seven", true]], "en", restarted);
  assert.equal(only(next.events, "skipped").length, 0);
  assert.equal(types(next.events).at(-1), "done");
});

test("after done nothing else happens", () => {
  const done = run("hello there", [[0, "hello there"]]);
  assert.deepEqual(run("", [[1, "hello there again"]], "en", done.state).events, []);
});

test("feeding never changes the previous state", () => {
  const start = createReadAlong(words("the dog ran"), { language: "en" });
  const before = JSON.stringify(start);
  feed(start, { id: 0, transcript: "the dog ran", isFinal: true });
  assert.equal(JSON.stringify(start), before);
});

test("bad input is tolerated", () => {
  const empty = createReadAlong([], { language: "en" });
  assert.deepEqual(feed(empty, { id: 0, transcript: "hello", isFinal: true }).events, []);
  const s = createReadAlong(words("hello there"), { language: "en" });
  assert.deepEqual(feed(s, null).events, []);
  assert.deepEqual(feed(s, { id: 0, transcript: 42, isFinal: true }).events, []);
});

test("a small word heard as another small word is not a mistake ('that' for 'the')", () => {
  const w = "Ever since tea was first imported the English have enjoyed a nice hot cup".split(" ").map((text, i) => ({ i, text, sentence: 0 }));
  const { state, events } = feed(createReadAlong(w, { language: "en" }), { id: 0, transcript: "ever since tea was first imported that english have enjoyed a nice hot cup", isFinal: true });
  assert.equal(events.some((e) => e.type === "differs" || e.type === "skipped"), false);
  assert.equal(Object.keys(state.read).length, w.length);
});

test("a dropped small word is not a skip, but a dropped content word still is", () => {
  const w = "We went to the old market and bought apples".split(" ").map((text, i) => ({ i, text, sentence: 0 }));
  const dropsThe = feed(createReadAlong(w, { language: "en" }), { id: 0, transcript: "we went to old market and bought apples", isFinal: true });
  assert.equal(dropsThe.events.some((e) => e.type === "skipped"), false);
  const dropsMarket = feed(createReadAlong(w, { language: "en" }), { id: 0, transcript: "we went to the old and bought apples", isFinal: true });
  assert.ok(dropsMarket.events.some((e) => e.type === "skipped" && e.word === "market"));
});

test("a content word heard as a different content word is still reported", () => {
  const w = "The dog chased the red ball across the yard".split(" ").map((text, i) => ({ i, text, sentence: 0 }));
  const { events } = feed(createReadAlong(w, { language: "en" }), { id: 0, transcript: "the dog chased the blue ball across the yard", isFinal: true });
  assert.ok(events.some((e) => e.type === "differs" && e.expected === "red"));
});

const LONG = ("The old lighthouse stood on a rocky cliff above the grey sea. Every evening the keeper climbed the winding stairs to light the great lamp. "
  + "Ships far away saw the beam and turned safely toward the harbor. One stormy night the lamp flickered and went out. "
  + "The keeper's daughter ran upstairs with a lantern and a box of matches. She worked through the wind until the flame caught again. "
  + "By morning every ship had reached the shore and the village cheered.").split(" ").map((text, i) => ({ i, text, sentence: 0 }));
const readLong = (transcript) => feed(createReadAlong(LONG, { language: "en" }), { id: 0, transcript, isFinal: true });

test("skipping a whole line is caught, not just the next word or two", () => {
  // the learner reads the first sentence, then jumps to "One stormy night" (skipping two full sentences)
  const { events } = readLong("the old lighthouse stood on a rocky cliff above the grey sea one stormy night the lamp flickered and went out");
  const skipped = events.find((e) => e.type === "skipped");
  assert.ok(skipped, "a long skip is reported");
  assert.equal(skipped.word, "Every");
  assert.ok(skipped.indexes.length >= 20, `${skipped.indexes.length} words skipped`);
  assert.equal(LONG[skipped.indexes.at(-1) + 1].text, "One");
});

test("skipping a paragraph near the end of the passage is caught", () => {
  const { events } = readLong("the old lighthouse stood on a rocky cliff above the grey sea by morning every ship had reached the shore and the village cheered");
  const skipped = events.find((e) => e.type === "skipped");
  assert.ok(skipped && skipped.indexes.length > 40, "most of the passage was skipped");
});

test("a few matching words far ahead do not count as a skip unless three in a row match", () => {
  // "the" and "of" are heard once each in the wrong place; it is noise, not a jump
  const { events } = readLong("the old lighthouse stood on a rocky cliff the sea of the");
  assert.equal(events.some((e) => e.type === "skipped" && e.indexes.length > 4), false);
});

test("reading the whole passage straight through still finishes with no stop", () => {
  const all = LONG.map((w) => w.text).join(" ");
  const { events } = readLong(all);
  assert.equal(events.some((e) => e.type === "skipped" || e.type === "differs"), false);
  assert.ok(events.some((e) => e.type === "done"));
});
