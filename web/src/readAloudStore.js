// Read-aloud results, kept in this browser's localStorage only, keyed by passage id (same approach as practice.js). Only counts are saved:
// never the audio, never the words that were heard. The last few sessions are kept so a reader can see progress; "Clear" removes them.
import { safeStorage } from "./practice.js";

const MAX_SESSIONS = 10;
export const resultsKey = (passageId) => `soundalong.readaloud.v1.${passageId}`;

const count = (n) => Number.isInteger(n) && n >= 0;
const validSession = (s) => s && Number.isFinite(s.at) && count(s.total) && count(s.read) && count(s.skipped) && count(s.retried);

/** Saved sessions, newest last. Blocked, missing or malformed storage gives an empty list. */
export function loadResults(passageId, storage = safeStorage()) {
  try {
    const parsed = JSON.parse(storage?.getItem(resultsKey(passageId)) ?? "null");
    return Array.isArray(parsed?.sessions) ? parsed.sessions.filter(validSession).map(({ at, total, read, skipped, retried }) => ({ at, total, read, skipped, retried })) : [];
  } catch {
    return [];
  }
}

/** Adds one session (returns the new list, or the old one when storage is unavailable). */
export function addResult(passageId, summary, at, storage = safeStorage()) {
  const before = loadResults(passageId, storage);
  const session = { at, total: summary.total, read: summary.read, skipped: summary.skipped, retried: summary.retried };
  if (!validSession(session)) return before;
  const sessions = [...before, session].slice(-MAX_SESSIONS);
  try {
    if (!storage) return before;
    storage.setItem(resultsKey(passageId), JSON.stringify({ sessions }));
    return sessions;
  } catch {
    return before;
  }
}

export function clearResults(passageId, storage = safeStorage()) {
  try {
    if (!storage) return false;
    storage.removeItem(resultsKey(passageId));
    return true;
  } catch {
    return false;
  }
}
