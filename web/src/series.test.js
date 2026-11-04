import { test } from "node:test";
import assert from "node:assert/strict";
import { groupSeries, neighborPart, seriesInfo } from "./series.js";

const IDS = ["2b781dab-4521-40d2-a9b6-ad5f2bb0ba90", "2b781dab-4521-40d2-a9b6-ad5f2bb0ba91", "2b781dab-4521-40d2-a9b6-ad5f2bb0ba92"];
const SID = "5af24980-4d6d-41c1-87fa-4f21cb2d169d";
const series = (index) => ({ id: SID, index, total: 3, title: "The Story", partIds: IDS });
const part = (index, extra = {}) => ({ id: IDS[index - 1], title: `The Story (Part ${index} of 3)`, words: 800, durationMs: 1000, language: "en", series: series(index), ...extra });

test("only a well-formed series description is accepted", () => {
  assert.equal(seriesInfo(part(2)).index, 2);
  assert.equal(seriesInfo({}), null);
  assert.equal(seriesInfo({ series: { ...series(2), total: 2 } }), null);
  assert.equal(seriesInfo({ series: { ...series(4) } }), null);
  assert.equal(seriesInfo({ series: { ...series(1), partIds: ["a", "b", "c"] } }), null);
});

test("the next and previous part exist only inside the document", async () => {
  const fetchTiming = async () => ({});
  assert.deepEqual(await neighborPart(part(1), 1, fetchTiming), { state: "ready", id: IDS[1] });
  assert.deepEqual(await neighborPart(part(2), -1, fetchTiming), { state: "ready", id: IDS[0] });
  assert.equal(await neighborPart(part(1), -1, fetchTiming), null);
  assert.equal(await neighborPart(part(3), 1, fetchTiming), null);
  assert.equal(await neighborPart({ id: "x" }, 1, fetchTiming), null);
});

test("a part that does not exist yet is reported as pending, not as an error", async () => {
  const notYet = async () => { throw new Error("404"); };
  assert.deepEqual(await neighborPart(part(1), 1, notYet), { state: "pending" });
});

test("a translated part leads to the translation of its neighbour, and is pending until that exists", async () => {
  const translated = { id: "es-2", language: "es", translationOf: { id: IDS[1] }, series: series(2) };
  const withLink = async (id) => (id === IDS[2] ? { translations: { es: { id: "es-3" } } } : { translations: { es: { id: "es-1" } } });
  assert.deepEqual(await neighborPart(translated, 1, withLink), { state: "ready", id: "es-3" });
  assert.deepEqual(await neighborPart(translated, -1, withLink), { state: "ready", id: "es-1" });
  assert.deepEqual(await neighborPart(translated, 1, async () => ({})), { state: "pending" });
});

test("the parts of a document become one Library entry where the first part was, in part order", () => {
  const other = { id: "solo", title: "Solo", words: 100, language: "en" };
  const out = groupSeries([other, part(2), part(1), part(3)]);
  assert.equal(out.length, 2);
  assert.equal(out[0], other);
  const doc = out[1];
  assert.equal(doc.isSeries, true);
  assert.equal(doc.title, "The Story");
  assert.deepEqual(doc.parts.map((p) => p.id), IDS);
  assert.equal(doc.words, 2400);
  assert.equal(doc.total, 3);
});

test("a document that is still being created shows the parts it has so far", () => {
  const out = groupSeries([part(1)]);
  assert.equal(out.length, 1);
  assert.equal(out[0].parts.length, 1);
  assert.equal(out[0].total, 3);
});

test("a language is offered for the whole document only when every part has it", () => {
  const both = groupSeries([part(1, { translationLangs: ["es"] }), part(2, { translationLangs: ["es"] }), part(3, { translationLangs: ["es"] })])[0];
  assert.deepEqual(both.translationLangs, ["es"]);
  const some = groupSeries([part(1, { translationLangs: ["es"] }), part(2), part(3, { translationLangs: ["es"] })])[0];
  assert.equal(some.translationLangs, undefined);
});

test("ordinary passages are returned untouched", () => {
  const list = [{ id: "a", title: "A" }, { id: "b", title: "B" }];
  assert.deepEqual(groupSeries(list), list);
});
