// The quiz attempt in progress, kept in memory only. Opening "Show me where" leaves the quiz screen; coming back (Back button) resumes
// exactly where the student was. Closing the tab forgets it. Finished scores are saved separately by quiz.js.
import { reactive } from "vue";

const attempts = new Map();
let counter = 0;

/** Order does not matter (the choices are reshuffled anyway); the set of published question ids does. */
export const signatureOf = (ids) => [...ids].sort().join("|");

const fresh = (docId, ids) => reactive({ seed: `${docId}:${Date.now()}:${(counter += 1)}`, signature: signatureOf(ids), answers: {}, index: 0, finished: false });

/** The attempt for these questions. Started when there is none, or when the published questions changed since it was saved. */
export function attemptFor(docId, ids) {
  const saved = attempts.get(docId);
  const stale = !saved || saved.signature !== signatureOf(ids) || saved.index >= Math.max(ids.length, 1);
  if (stale) attempts.set(docId, fresh(docId, ids));
  return attempts.get(docId);
}

/** Retry: a new attempt, with the choices shuffled again. */
export function restartAttempt(docId, ids) {
  attempts.set(docId, fresh(docId, ids));
  return attempts.get(docId);
}
