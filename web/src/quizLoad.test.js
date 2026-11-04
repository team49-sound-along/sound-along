import { test } from "node:test";
import assert from "node:assert/strict";
import { loadQuiz } from "./quizLoad.js";
import { fetchQuestions } from "./api.js";

const doc = (n) => ({ reviewed: true, questions: Array.from({ length: n }, (_, i) => ({ id: `q${i}`, question: "Q?", choices: ["a", "b"], answerIndex: 0, evidenceSentence: i })) });
const fakeFetch = (docs) => { const asked = []; const fn = async (id) => { asked.push(id); return docs[id] ?? null; }; fn.asked = asked; return fn; };

test("a passage with its own questions makes one request", async () => {
  const f = fakeFetch({ me: doc(2), pair: doc(1) });
  const quiz = await loadQuiz("me", { pairId: "pair" }, f);
  assert.equal(quiz.questions.length, 2);
  assert.deepEqual(f.asked, ["me"]);
});

test("it falls back to the pair, then to the other language, and says which language", async () => {
  assert.equal((await loadQuiz("me", { pairId: "pair" }, fakeFetch({ pair: doc(1) }))).docId, "pair");
  const other = await loadQuiz("es1", { language: "es", translationOf: { id: "en1", lang: "en", sentenceMap: [0] } }, fakeFetch({ en1: doc(3) }));
  assert.equal(other.otherLanguage, "en");
  assert.equal(other.readerId, "en1");
});

test("no approved questions anywhere gives null", async () => {
  assert.equal(await loadQuiz("me", { pairId: "pair" }, fakeFetch({ me: { reviewed: false, questions: doc(2).questions } })), null);
});

test("fetchQuestions gives null for a missing, broken or non-object document and never throws", async () => {
  const res = (ok, body) => async () => ({ ok, json: async () => { if (body === "bad") throw new SyntaxError("x"); return body; } });
  assert.deepEqual(await fetchQuestions("a", res(true, { reviewed: true })), { reviewed: true });
  for (const f of [res(false, {}), res(true, "bad"), res(true, []), res(true, null), async () => { throw new Error("offline"); }]) assert.equal(await fetchQuestions("a", f), null);
  let url;
  await fetchQuestions("a b", async (u) => { url = u; return { ok: false }; });
  assert.equal(url, "/data/a%20b.questions.json");
});
