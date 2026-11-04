import { test } from "node:test";
import assert from "node:assert/strict";
import { followAction } from "./readerFollow.js";

const at = (top, bottom) => ({ top, bottom });

test("a word that is on screen needs nothing, whatever the setting", () => {
  assert.equal(followAction({ reduce: false, rect: at(300, 340), bottomLimit: 700 }), "none");
  assert.equal(followAction({ reduce: true, rect: at(300, 340), bottomLimit: 700 }), "none");
});

test("a word that left the screen is followed by scrolling, or with Reduce motion by an offer to jump (the page never moves by itself)", () => {
  assert.equal(followAction({ reduce: false, rect: at(720, 760), bottomLimit: 700 }), "scroll");
  assert.equal(followAction({ reduce: true, rect: at(720, 760), bottomLimit: 700 }), "offer-jump");
  assert.equal(followAction({ reduce: true, rect: at(20, 60), bottomLimit: 700 }), "offer-jump", "above the screen counts too");
  assert.equal(followAction({ reduce: false, rect: at(150, 190), bottomLimit: 700 }), "scroll", "under the top bar counts as off screen");
});
