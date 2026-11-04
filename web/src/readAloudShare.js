// What one read-aloud session shares with the teacher, and only if the class allows it. Counts and word positions only: never the audio,
// never what was heard, never a name. The server looks the word up in the passage itself.
import { summarize } from "./readAloud.js";

export const MAX_FLAGS = 50;
export const MAX_RETRIES = 20;

export const readAloudSettingsFor = (view, classId) => {
  const mine = classId ? view?.classes?.find((c) => c.id === classId) : null;
  const source = mine ?? view?.defaults;
  return source ? { mic: source.mic === true, share: source.share === true, readers: source.readers === true } : { mic: false, share: false, readers: false };
};

/**
 * @param state follower state from readAloud.js
 * @returns the payload for POST /read-aloud/results, or null when there is nothing to share
 */
export function buildSharePayload({ passageId, classId, language, state, readerCode }) {
  const total = state.targets.length;
  if (total === 0) return null;
  const { read, retried } = summarize(state);
  const skipped = [...new Set(state.skippedEver)];
  const differs = [...new Set(state.differsEver)].filter((i) => !skipped.includes(i)); // a position is sent once, as skipped first
  const words = [...skipped.sort((a, b) => a - b).map((i) => ({ i, kind: "skipped" })), ...differs.sort((a, b) => a - b).map((i) => ({ i, kind: "differs" }))].slice(0, MAX_FLAGS);
  return {
    passageId,
    ...(classId ? { classId } : {}),
    language: language === "es" ? "es" : "en",
    wordsTotal: total,
    wordsRead: read,
    finished: read === total,
    retried: Math.min(retried, MAX_RETRIES),
    words,
    ...(readerCode ? { readerCode } : {}),
  };
}
