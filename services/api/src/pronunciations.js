import { HttpError } from "./http.js";

const WORD = /^[a-z'-]{1,40}$/;
const PLAIN = /^[A-Za-z][A-Za-z -]*$/;
const PHONEMES = /^\/[^/\p{C}<>]+\/$/u;
const MAX_RESPELLING = 60;

const bad = (message) => {
  throw new HttpError(400, message);
};

/** Lowercase and validate a word taken from a URL or body. */
export function parseWord(value) {
  const word = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (!WORD.test(word)) bad("A word can use letters, apostrophes and hyphens only, up to 40 characters.");
  return word;
}

export function parseRespelling(body) {
  if (body === null || typeof body !== "object" || Array.isArray(body)) bad("Send a JSON object.");
  const respelling = typeof body.respelling === "string" ? body.respelling.trim() : "";
  if (respelling.length < 1 || respelling.length > MAX_RESPELLING) bad(`The respelling must be 1 to ${MAX_RESPELLING} characters.`);
  if (!PLAIN.test(respelling) && !PHONEMES.test(respelling)) {
    bad('Write the respelling with letters, spaces and hyphens ("gay-uh-teez"), or phonemes between slashes ("/ɡˈAɪtˌiz/").');
  }
  return respelling;
}

/** Pronunciation[] -> { word: respelling }, the shape the generator reads. */
export const toPronunciationMap = (list) => Object.fromEntries(list.map((p) => [p.word, p.respelling]));
