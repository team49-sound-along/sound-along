import assert from "node:assert/strict";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, describe, test } from "node:test";
import { startLocalApp } from "./support/harness.js";

const P1 = "2b781dab-4521-40d2-a9b6-ad5f2bb0ba98";
const P2 = "3c781dab-4521-40d2-a9b6-ad5f2bb0ba99";
const AI1 = "aaaaaaaaaaaaaaa1";
const HU1 = "bbbbbbbbbbbbbbb1";
const PO1 = "cccccccccccccc01";
const AI2 = "aaaaaaaaaaaaaaa2";
const HU2 = "bbbbbbbbbbbbbbb2";
const MANIFEST = [
  { token: AI1, passageId: P1, title: "Park", kind: "ai" },
  { token: HU1, passageId: P1, title: "Park", kind: "human" },
  { token: PO1, passageId: P1, title: "Park", kind: "polly_current" },
  { token: AI2, passageId: P2, title: "Bees", kind: "ai" },
  { token: HU2, passageId: P2, title: "Bees", kind: "human" },
];
const RATER = "11111111-1111-4111-8111-111111111111";
const TRIAL = "22222222-2222-4222-8222-222222222222";
const good = (over = {}) => ({ trialId: TRIAL, aToken: AI1, bToken: HU1, preferred: "a", ratingA: 5, ratingB: 3, ...over });

async function withAb(manifest, { config } = {}) {
  const dir = await mkdtemp(path.join(tmpdir(), "ab-"));
  if (manifest) {
    await mkdir(path.join(dir, "ab"));
    await writeFile(path.join(dir, "ab", "manifest.json"), JSON.stringify(manifest));
    for (const c of manifest) await writeFile(path.join(dir, "ab", `${c.token}.mp3`), Buffer.from("0123456789abcdef"));
  }
  return startLocalApp({ dir, config });
}

describe("GET /api/ratings/trial", async () => {
  const ctx = await withAb(MANIFEST);
  after(() => ctx.close());

  test("returns an AI-vs-other pair of one passage with urls and no kinds", async () => {
    const kindsSeen = new Set();
    for (let i = 0; i < 30; i += 1) {
      const { json } = await ctx.call("GET", "/api/ratings/trial");
      const t = json.data;
      assert.deepEqual(Object.keys(t).sort(), ["a", "b", "prompt", "title", "trialId"]);
      assert.match(t.trialId, /^[0-9a-f-]{36}$/);
      assert.equal(t.prompt, "Which narration sounds more natural to read along with?");
      assert.equal(t.a.url, `/data/ab/${t.a.token}.mp3`);
      assert.deepEqual(Object.keys(t.a).sort(), ["token", "url"]);
      const kinds = [t.a, t.b].map((c) => MANIFEST.find((m) => m.token === c.token));
      assert.equal(kinds[0].passageId, kinds[1].passageId);
      assert.equal(kinds.filter((k) => k.kind === "ai").length, 1);
      assert.ok(!/ai|human|polly/i.test(JSON.stringify({ a: t.a, b: t.b })), "no kind leaks");
      kindsSeen.add(`${kinds[0].kind}/${kinds[1].kind}`);
    }
    assert.ok(kindsSeen.size > 1, "a/b order and partner vary");
  });

  test("two calls give different trial ids", async () => {
    const [x, y] = [await ctx.call("GET", "/api/ratings/trial"), await ctx.call("GET", "/api/ratings/trial")];
    assert.notEqual(x.json.data.trialId, y.json.data.trialId);
  });
});

describe("trial eligibility", async () => {
  test("null when there is no manifest, an empty one, or no passage with ai plus another clip", async () => {
    for (const manifest of [null, [], [{ token: AI1, passageId: P1, title: "x", kind: "ai" }], [{ token: HU1, passageId: P1, title: "x", kind: "human" }, { token: PO1, passageId: P1, title: "x", kind: "polly_current" }]]) {
      const ctx = await withAb(manifest);
      const r = await ctx.call("GET", "/api/ratings/trial");
      assert.equal(r.status, 200);
      assert.equal(r.json.data, null);
      ctx.close();
    }
  });

  test("ignores malformed manifest entries", async () => {
    const ctx = await withAb([{ token: "short", passageId: P1, kind: "ai" }, { token: HU1, passageId: P1, kind: "human" }]);
    assert.equal((await ctx.call("GET", "/api/ratings/trial")).json.data, null);
    ctx.close();
  });
});

describe("POST /api/ratings and summary", async () => {
  const ctx = await withAb(MANIFEST);
  after(() => ctx.close());
  const { call } = ctx;

  test("empty summary and insights blindRating null before any rating", async () => {
    const s = (await call("GET", "/api/ratings/summary")).json.data;
    assert.equal(s.ratings, 0);
    assert.equal(s.raters, 0);
    assert.deepEqual(s.meanRating, { ai: null, human: null, polly_current: null });
    assert.deepEqual(s.comparisons.map((c) => [c.comparison, c.n]), [["ai vs human", 0], ["ai vs polly_current", 0]]);
    assert.equal((await call("GET", "/api/insights")).json.data.quality.blindRating, null);
  });

  test("rejects bad bodies with readable messages and stores nothing", async () => {
    const cases = [
      [[], /JSON object/],
      [good({ trialId: "nope" }), /listening round/],
      [good({ aToken: "XYZ" }), /clips are not valid/],
      [good({ bToken: undefined }), /clips are not valid/],
      [good({ aToken: "deadbeefdeadbeef" }), /could not find/],
      [good({ bToken: AI2 }), /same passage/],
      [good({ aToken: AI1, bToken: AI1 }), /same passage/],
      [good({ aToken: HU1, bToken: PO1 }), /AI voice/],
      [good({ preferred: "c" }), /"a", "b" or "tie"/],
      [good({ ratingA: 0 }), /clip A.*1 to 5/],
      [good({ ratingB: 6 }), /clip B.*1 to 5/],
      [good({ ratingA: 2.5 }), /whole number/],
      [good({ ratingB: "5" }), /whole number/],
      [good({ raterId: "abc" }), /listener id/],
    ];
    for (const [body, pattern] of cases) {
      const r = await call("POST", "/api/ratings", body);
      assert.equal(r.status, 400, JSON.stringify(body));
      assert.match(r.json.error, pattern);
    }
    assert.equal((await call("GET", "/api/ratings/summary")).json.data.ratings, 0);
  });

  test("tampered tokens: path-like, uppercase, and cross-passage pairs are rejected", async () => {
    for (const aToken of ["../../state.json", AI1.toUpperCase()]) {
      assert.equal((await call("POST", "/api/ratings", good({ aToken }))).status, 400);
    }
    assert.equal((await call("POST", "/api/ratings", good({ aToken: AI2, bToken: HU1 }))).status, 400);
  });

  test("records ratings, in either order, and the summary matches hand-computed values", async () => {
    const posts = [
      good({ raterId: RATER }), // ai(5) vs human(3), ai preferred
      good({ aToken: HU1, bToken: AI1, preferred: "a", ratingA: 4, ratingB: 2, raterId: RATER }), // human preferred
      good({ aToken: PO1, bToken: AI1, preferred: "tie", ratingA: 3, ratingB: 3 }), // tie, anonymous
      good({ aToken: AI2, bToken: HU2, preferred: "b", ratingA: 1, ratingB: 5 }), // human preferred, anonymous
    ];
    for (const body of posts) {
      const r = await call("POST", "/api/ratings", body);
      assert.equal(r.status, 200);
      assert.deepEqual(r.json.data, { recorded: true });
    }
    const s = (await call("GET", "/api/ratings/summary")).json.data;
    assert.equal(s.ratings, 4);
    assert.equal(s.raters, 3); // RATER + 2 anonymous
    assert.deepEqual(s.comparisons, [
      { comparison: "ai vs human", n: 3, preferredAi: 1, preferredOther: 2, tie: 0 },
      { comparison: "ai vs polly_current", n: 1, preferredAi: 0, preferredOther: 0, tie: 1 },
    ]);
    // ai scores: 5,2,3,1 = 11/4; human: 3,4,5 = 4; polly: 3
    assert.deepEqual(s.meanRating, { ai: 2.75, human: 4, polly_current: 3 });
    const insights = (await call("GET", "/api/insights")).json.data;
    assert.deepEqual(insights.quality.blindRating, s);
  });
});

describe("rating writes share the limiter and kill switch", async () => {
  test("429 after the write limit and 503 when generation is off", async () => {
    const limited = await withAb(MANIFEST, { config: { writePerMinute: 2 } });
    const codes = [];
    for (let i = 0; i < 3; i += 1) codes.push((await limited.call("POST", "/api/ratings", good())).status);
    assert.deepEqual(codes, [200, 200, 429]);
    limited.close();
    const off = await withAb(MANIFEST, { config: { generationEnabled: false } });
    const r = await off.call("POST", "/api/ratings", good());
    assert.equal(r.status, 503);
    assert.match(r.json.error, /paused/);
    assert.equal((await off.call("GET", "/api/ratings/trial")).status, 200);
    off.close();
  });
});

describe("GET /data/ab/:token.mp3", async () => {
  const ctx = await withAb(MANIFEST);
  after(() => ctx.close());

  test("serves a clip as audio with Range support", async () => {
    const full = await fetch(`${ctx.base}/data/ab/${AI1}.mp3`);
    assert.equal(full.status, 200);
    assert.match(full.headers.get("content-type"), /audio\/mpeg/);
    assert.equal((await full.text()).length, 16);
    const part = await fetch(`${ctx.base}/data/ab/${AI1}.mp3`, { headers: { range: "bytes=2-5" } });
    assert.equal(part.status, 206);
    assert.equal(await part.text(), "2345");
  });

  test("manifest, short, uppercase, traversal and unknown tokens are 404", async () => {
    for (const file of ["manifest.json", "abc.mp3", `${AI1.toUpperCase()}.mp3`, "..%2Fstate.json", "ffffffffffffffff.mp3", `${AI1}.mp3.bak`]) {
      const r = await fetch(`${ctx.base}/data/ab/${file}`);
      assert.equal(r.status, 404, file);
    }
  });

  test("404 when no data dir is configured (AWS serves these through CloudFront)", async () => {
    const aws = await startLocalApp({ config: { dataDir: undefined } });
    assert.equal((await fetch(`${aws.base}/data/ab/${AI1}.mp3`)).status, 404);
    assert.equal((await aws.call("GET", "/api/ratings/trial")).json.data, null);
    aws.close();
  });
});
