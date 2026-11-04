import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { annotateTokens, heatLevel, missedText, topWordRows, wordKey } from "./heatMap.js";

describe("heatLevel", () => {
  test("zero means not shaded; the share of reads picks one of four levels", () => {
    assert.equal(heatLevel(0, 14), 0);
    assert.equal(heatLevel(2, 14), 1);
    assert.equal(heatLevel(4, 14), 2);
    assert.equal(heatLevel(7, 14), 3);
    assert.equal(heatLevel(14, 14), 4);
    assert.equal(heatLevel(3, 0), 0);
  });
});

describe("missedText", () => {
  test("plain words for the tap or hover", () => {
    assert.equal(missedText(6, 14), "Missed by 6 of 14 readers");
    assert.equal(missedText(1, 1), "Missed by 1 of 1 readers");
  });
});

describe("wordKey", () => {
  test("letters only, lower case", () => {
    assert.equal(wordKey("“Laughed.”"), "laughed");
  });
});

describe("annotateTokens", () => {
  const tokens = [
    { i: 0, text: "The", paragraph: 0, missed: 0 },
    { i: 1, text: "kite", paragraph: 0, missed: 7 },
    { i: 2, text: "dragged.", paragraph: 1, missed: 14 },
    { i: 3, text: "dragged", paragraph: 1, missed: 2 },
  ];
  test("groups by paragraph and marks levels; the top words get a marker in every place they appear", () => {
    const out = annotateTokens(tokens, 14, new Set(["dragged"]));
    assert.equal(out.length, 2);
    assert.deepEqual(out[0].map((t) => [t.text, t.level, t.top]), [["The", 0, false], ["kite", 3, false]]);
    assert.deepEqual(out[1].map((t) => [t.text, t.level, t.top]), [["dragged.", 4, true], ["dragged", 1, true]]);
    assert.equal(out[1][0].title, "Missed by 14 of 14 readers");
    assert.equal(out[0][0].title, "");
  });
});

describe("topWordRows", () => {
  test("a ranked list of at most five words, the text alternative to the colours", () => {
    const items = Array.from({ length: 7 }, (_, n) => ({ word: `w${n}`, missed: 10 - n, sessions: 14 }));
    const rows = topWordRows(items);
    assert.equal(rows.length, 5);
    assert.deepEqual(rows[0], { word: "w0", text: "Missed by 10 of 14 readers", rank: 1 });
  });
});
