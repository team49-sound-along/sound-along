import { HttpError } from "../http.js";

export const MAX_FLAGS = 50;
export const MAX_RETRIES = 20;
const KINDS = new Set(["skipped", "differs"]);
const TOP_KEYS = new Set(["passageId", "classId", "language", "wordsTotal", "wordsRead", "finished", "retried", "words", "readerCode"]);
/** An opaque random token made on the reader's own device (no I, L, O, 0 or 1). Never a name or anything derived from the person. */
export const READER_CODE = /^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{8,12}$/;
const bad = (message) => {
  throw new HttpError(400, message);
};
const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const isCount = (n, max) => Number.isInteger(n) && n >= 0 && n <= max;

function parseFlags(list, indexes) {
  if (!Array.isArray(list) || list.length > MAX_FLAGS) bad(`Send at most ${MAX_FLAGS} words.`);
  const seen = new Set();
  return list.map((entry) => {
    if (!isObject(entry) || Object.keys(entry).some((k) => k !== "i" && k !== "kind")) bad("Each word needs only a position and a kind.");
    if (!Number.isInteger(entry.i) || !indexes.has(entry.i)) bad("That word position is not in the passage.");
    if (!KINDS.has(entry.kind)) bad('A word kind is "skipped" or "differs".');
    if (seen.has(entry.i)) bad("Each word may appear once.");
    seen.add(entry.i);
    return { i: entry.i, kind: entry.kind };
  });
}

/**
 * Validates one anonymous read-aloud result. Counts and word positions only: no audio, no transcript, no names or ids.
 * `timing` is the passage's own timing document (looked up by the server, never taken from the client): it bounds the numbers and
 * says which positions are real words. The text of a word is looked up from it later and is never sent by the client.
 * `finished` and `retried` are the two fields beyond the minimum: without them a finish rate and a retry rate cannot be told.
 */
export function parseReadAloudResult(body, { passageIds, classIds, timing }) {
  if (!isObject(body)) bad("Send a JSON object.");
  if (Object.keys(body).some((k) => !TOP_KEYS.has(k))) bad("Unknown field.");
  if (!passageIds.has(body.passageId)) bad("Unknown passage.");
  if (body.classId != null && !(typeof body.classId === "string" && classIds.has(body.classId))) bad("Unknown class.");
  const words = Array.isArray(timing?.words) ? timing.words : null;
  if (!words) bad("Unknown passage.");
  if (body.language !== (timing.language === "es" ? "es" : "en")) bad("The language does not match the passage.");
  if (!Number.isInteger(body.wordsTotal) || body.wordsTotal < 1 || body.wordsTotal > words.length) bad("Word count out of range.");
  if (!isCount(body.wordsRead, body.wordsTotal)) bad("Words read out of range.");
  if (typeof body.finished !== "boolean" || body.finished !== (body.wordsRead === body.wordsTotal)) bad("The result does not add up.");
  if (!isCount(body.retried, MAX_RETRIES)) bad("Tries out of range.");
  if (body.readerCode != null && !(typeof body.readerCode === "string" && READER_CODE.test(body.readerCode))) bad("That reader code is not valid.");
  const real = new Set(words.filter((w) => Number.isInteger(w?.i) && /[\p{L}\p{N}]/u.test(String(w.text ?? ""))).map((w) => w.i));
  return {
    passageId: body.passageId,
    classId: body.classId ?? null,
    language: body.language,
    wordsTotal: body.wordsTotal,
    wordsRead: body.wordsRead,
    finished: body.finished,
    retried: body.retried,
    words: parseFlags(body.words, real),
    readerCode: body.readerCode ?? null,
  };
}
