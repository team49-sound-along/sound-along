// An anonymous reader code for this device: random, kept only in this browser's localStorage, never made from anything about the person
// (no name, account, device details or time). It is sent with a read-aloud result only when the teacher has switched on "Show progress by
// reader" for the class. A shared classroom device is one reader; "Start a new reader code" makes a fresh one.
import { safeStorage } from "./practice.js";

export const READER_KEY = "soundalong.readerCode.v1";
export const ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"; // no I, L, O, 0 or 1: easy to read out loud
export const CODE_LENGTH = 8;
export const CODE_PATTERN = /^[ABCDEFGHJKMNPQRSTUVWXYZ23456789]{8,12}$/;

/** A new random code. `random(n)` returns n random bytes; it defaults to the browser's crypto. */
export function makeReaderCode(random = (n) => globalThis.crypto.getRandomValues(new Uint8Array(n))) {
  const limit = 256 - (256 % ALPHABET.length); // bytes at or above this are skipped so every letter is equally likely
  let out = "";
  while (out.length < CODE_LENGTH) {
    for (const byte of random(CODE_LENGTH * 2)) {
      if (byte < limit && out.length < CODE_LENGTH) out += ALPHABET[byte % ALPHABET.length];
    }
  }
  return out;
}

/** The saved code, or a new one saved now. Blocked storage gives null: nothing can be remembered, so no code is sent. */
export function readerCode(storage = safeStorage(), random) {
  try {
    if (!storage) return null;
    const saved = storage.getItem(READER_KEY);
    if (saved && CODE_PATTERN.test(saved)) return saved;
    const fresh = makeReaderCode(random);
    storage.setItem(READER_KEY, fresh);
    return fresh;
  } catch {
    return null;
  }
}

/** "Start a new reader code": returns the new code (null when storage is blocked). */
export function startNewReaderCode(storage = safeStorage(), random) {
  try {
    storage?.removeItem(READER_KEY);
  } catch {
    return null;
  }
  return readerCode(storage, random);
}

/** "K7Q29XMA" -> "Reader K7Q2 9XMA" (for reading out loud). */
export const readerLabel = (code) => (code ? `Reader ${code.slice(0, 4)} ${code.slice(4)}` : "");
